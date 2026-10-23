"""
Test script for MODULE 4: Duplicate Detection stage.
Validates:
1. Base certificate: initial scan
2. Test 1: Upload the same file twice -> EXACT hash match
3. Test 2: Upload a re-saved/re-scanned version (different sha256_hash) -> PERCEPTUAL hash match
4. Test 3: Upload with same register_number & matching name -> IDENTITY match
5. Test 4: Upload with same register_number & conflicting name -> IDENTITY CONFLICT
6. Test 5: Upload completely different certificate -> NO DUPLICATE
7. Validates owner distinction (same owner vs different owner)
8. Prints match_reason and database fields for each case
"""
import asyncio
import os
import sys
import uuid
import hashlib
import cv2
import numpy as np

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, backend_dir)

from sqlalchemy import select
from app.db.database import AsyncSessionLocal, init_db
from app.models.models import Certificate, User, UserRole, OCRData, VerificationResult, VerificationJob
from app.api.verification import run_duplicate_detection
from app.services.storage_service import get_storage_backend
from app.services.image_preprocessing import load_image_as_array


async def main():
    await init_db()
    async with AsyncSessionLocal() as db:
        storage = get_storage_backend()

        print("\n=======================================================")
        print("MODULE 4: DUPLICATE DETECTION TEST SUITE")
        print("=======================================================")

        # Load user and base certificate
        orig_cert_id = "b4d835cd6e81412692317d3854a156f5"
        cert_res = await db.execute(select(Certificate).where(Certificate.id == orig_cert_id))
        orig_cert = cert_res.scalar_one_or_none()
        assert orig_cert is not None, f"Original certificate {orig_cert_id} not found!"

        user_res = await db.execute(select(User).where(User.id == orig_cert.owner_id))
        user = user_res.scalar_one_or_none()
        assert user is not None, f"User {orig_cert.owner_id} not found!"

        # Cleanup any test certificates from previous test executions
        test_filenames = [
            "Keerthana_12th_Marksheet_COPY.pdf",
            "Keerthana_12th_Marksheet_RECOMPRESSED.jpg",
            "Keerthana_Degree_Cert.jpg",
            "Stolen_Reg_Cert.jpg",
            "Unique_Independent_Cert.jpg",
        ]
        old_test_certs = (await db.execute(
            select(Certificate).where(Certificate.original_filename.in_(test_filenames))
        )).scalars().all()
        for oc in old_test_certs:
            # Delete related jobs and verification results
            vr_old = (await db.execute(select(VerificationResult).where(VerificationResult.certificate_id == oc.id))).scalars().all()
            for v in vr_old:
                await db.delete(v)
            vj_old = (await db.execute(select(VerificationJob).where(VerificationJob.certificate_id == oc.id))).scalars().all()
            for j in vj_old:
                await db.delete(j)
            ocr_old = (await db.execute(select(OCRData).where(OCRData.certificate_id == oc.id))).scalars().all()
            for o in ocr_old:
                await db.delete(o)
            await db.delete(oc)
        await db.commit()

        # Ensure OCR data exists for original certificate
        ocr_res = await db.execute(select(OCRData).where(OCRData.certificate_id == orig_cert_id))
        orig_ocr = ocr_res.scalar_one_or_none()
        if not orig_ocr:
            orig_ocr = OCRData(
                id=uuid.uuid4().hex,
                certificate_id=orig_cert_id,
                student_name="Keerthana K",
                register_number="REG-TN-2023-91823",
                certificate_number="HSC-2023-091823",
            )
            db.add(orig_ocr)
            await db.commit()

        # Create a second user in the same org for testing different-owner detection
        user_b_res = await db.execute(
            select(User).where(User.organization_id == user.organization_id, User.id != user.id)
        )
        user_b = user_b_res.scalars().first()
        if not user_b:
            user_b = User(
                id=uuid.uuid4().hex,
                email="investigator@acme.edu",
                hashed_password="hash",
                full_name="Investigator Agent",
                organization_id=user.organization_id,
                role=UserRole.VERIFIER,
                is_active=True,
                is_email_verified=True,
            )
            db.add(user_b)
            await db.commit()

        # Run duplicate detection on original certificate
        vr_orig = await run_duplicate_detection(orig_cert_id, user=user, db=db)
        print(f"\n[0. Base Certificate Scan]")
        print(f"   ID:           {orig_cert.id}")
        print(f"   is_duplicate: {vr_orig.is_duplicate}")
        print(f"   match_reason: {vr_orig.duplicate_match_reason}")

        # -------------------------------------------------------------
        # TEST 1: Same File Uploaded Twice (Exact SHA-256 match)
        # -------------------------------------------------------------
        print("\n-------------------------------------------------------")
        print("TEST 1: Upload the SAME FILE twice (Exact SHA-256 match)")
        print("-------------------------------------------------------")
        cert1_id = uuid.uuid4().hex
        cert1 = Certificate(
            id=cert1_id,
            organization_id=user.organization_id,
            owner_id=user.id,
            original_filename="Keerthana_12th_Marksheet_COPY.pdf",
            storage_path=orig_cert.storage_path,
            file_type=orig_cert.file_type,
            file_size_bytes=orig_cert.file_size_bytes,
            sha256_hash=orig_cert.sha256_hash,
        )
        db.add(cert1)
        job1 = VerificationJob(
            id=uuid.uuid4().hex,
            organization_id=user.organization_id,
            certificate_id=cert1_id,
            stage_states={},
        )
        db.add(job1)
        await db.commit()

        vr1 = await run_duplicate_detection(cert1_id, user=user, db=db)
        print(f"-> Test 1 Results:")
        print(f"   is_duplicate:                {vr1.is_duplicate}")
        print(f"   duplicate_of_certificate_id: {vr1.duplicate_of_certificate_id}")
        print(f"   match_layer:                 {vr1.duplicate_detail.get('match_layer')}")
        print(f"   owner_distinction:           {vr1.duplicate_detail.get('owner_distinction')}")
        print(f"   duplicate_match_reason:\n     \"{vr1.duplicate_match_reason}\"")
        assert vr1.is_duplicate is True
        assert vr1.duplicate_detail.get("match_layer") == "EXACT"
        assert vr1.duplicate_detail.get("same_owner") is True

        # -------------------------------------------------------------
        # TEST 2: Re-saved or Re-scanned Version (Perceptual match)
        # -------------------------------------------------------------
        print("\n-------------------------------------------------------")
        print("TEST 2: Re-saved / Re-scanned Version (Perceptual match)")
        print("-------------------------------------------------------")
        orig_bytes = await storage.read(orig_cert.storage_path)
        orig_arr = load_image_as_array(orig_bytes, orig_cert.file_type)

        # Re-save with JPEG compression (quality 60) and slight brightness offset (+8)
        # to simulate scanner/photo variation with a DIFFERENT file hash
        resaved_arr = np.clip(orig_arr.astype(np.int16) + 8, 0, 255).astype(np.uint8)
        _, enc_jpg = cv2.imencode(".jpg", resaved_arr, [cv2.IMWRITE_JPEG_QUALITY, 60])
        resaved_bytes = enc_jpg.tobytes()
        resaved_hash = hashlib.sha256(resaved_bytes).hexdigest()
        assert resaved_hash != orig_cert.sha256_hash, "Hash should differ for re-saved version!"

        resaved_storage_path = await storage.save_bytes(resaved_bytes, "marksheet_resaved.jpg")

        cert2_id = uuid.uuid4().hex
        cert2 = Certificate(
            id=cert2_id,
            organization_id=user.organization_id,
            owner_id=user.id,
            original_filename="Keerthana_12th_Marksheet_RECOMPRESSED.jpg",
            storage_path=resaved_storage_path,
            file_type="jpg",
            file_size_bytes=len(resaved_bytes),
            sha256_hash=resaved_hash,
        )
        db.add(cert2)
        job2 = VerificationJob(
            id=uuid.uuid4().hex,
            organization_id=user.organization_id,
            certificate_id=cert2_id,
            stage_states={},
        )
        db.add(job2)
        await db.commit()

        vr2 = await run_duplicate_detection(cert2_id, user=user, db=db)
        print(f"-> Test 2 Results:")
        print(f"   is_duplicate:                {vr2.is_duplicate}")
        print(f"   duplicate_of_certificate_id: {vr2.duplicate_of_certificate_id}")
        print(f"   match_layer:                 {vr2.duplicate_detail.get('match_layer')}")
        print(f"   owner_distinction:           {vr2.duplicate_detail.get('owner_distinction')}")
        print(f"   perceptual_hash_match:       {vr2.duplicate_detail.get('perceptual_hash_match')}")
        print(f"   visual_similarity:           {vr2.duplicate_detail.get('visual_similarity')}%")
        print(f"   duplicate_match_reason:\n     \"{vr2.duplicate_match_reason}\"")
        assert vr2.is_duplicate is True
        assert vr2.duplicate_detail.get("match_layer") in ("EXACT", "PERCEPTUAL")

        # -------------------------------------------------------------
        # TEST 3: Different File with Same Register Number (Identity match)
        # -------------------------------------------------------------
        print("\n-------------------------------------------------------")
        print("TEST 3: Same Register Number & Matching Student Name")
        print("-------------------------------------------------------")
        # Distinct image (synthetic degree certificate with distinct high-contrast colors & pattern)
        run_nonce = uuid.uuid4().hex[:8]
        id_img = np.full((600, 400, 3), (35, 45, 55), dtype=np.uint8)
        cv2.rectangle(id_img, (0, 0), (400, 110), (160, 90, 40), -1)
        cv2.rectangle(id_img, (30, 220), (370, 270), (80, 80, 130), -1)
        cv2.putText(id_img, "ANNAMALAI UNIVERSITY", (30, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(id_img, "Degree Certificate", (30, 160), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 220, 255), 1)
        cv2.putText(id_img, f"Ref {run_nonce}", (40, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        _, enc_id = cv2.imencode(".jpg", id_img)
        id_bytes = enc_id.tobytes()
        id_hash = hashlib.sha256(id_bytes).hexdigest()
        id_storage_path = await storage.save_bytes(id_bytes, f"degree_different_{run_nonce}.jpg")

        cert3_id = uuid.uuid4().hex
        cert3 = Certificate(
            id=cert3_id,
            organization_id=user.organization_id,
            owner_id=user_b.id,  # uploaded by User B (different owner)
            original_filename="Keerthana_Degree_Cert.jpg",
            storage_path=id_storage_path,
            file_type="jpg",
            file_size_bytes=len(id_bytes),
            sha256_hash=id_hash,
        )
        db.add(cert3)
        # Same register number as Keerthana's marksheet and matching fuzzy name
        ocr3 = OCRData(
            id=uuid.uuid4().hex,
            certificate_id=cert3_id,
            register_number=orig_ocr.register_number,
            student_name="keerthana k.",  # fuzzy match
        )
        db.add(ocr3)
        job3 = VerificationJob(
            id=uuid.uuid4().hex,
            organization_id=user.organization_id,
            certificate_id=cert3_id,
            stage_states={},
        )
        db.add(job3)
        await db.commit()

        vr3 = await run_duplicate_detection(cert3_id, user=user_b, db=db)
        print(f"-> Test 3 Results:")
        print(f"   is_duplicate:                {vr3.is_duplicate}")
        print(f"   duplicate_of_certificate_id: {vr3.duplicate_of_certificate_id}")
        print(f"   match_layer:                 {vr3.duplicate_detail.get('match_layer')}")
        print(f"   owner_distinction:           {vr3.duplicate_detail.get('owner_distinction')}")
        print(f"   registration_number_match:   {vr3.duplicate_detail.get('registration_number_match')}")
        print(f"   duplicate_match_reason:\n     \"{vr3.duplicate_match_reason}\"")
        assert vr3.is_duplicate is True
        assert vr3.duplicate_detail.get("match_layer") == "IDENTITY"
        assert vr3.duplicate_detail.get("owner_distinction") == "DIFFERENT_OWNER_DUPLICATE"

        # -------------------------------------------------------------
        # TEST 4: Identity Conflict (Same Register No, Conflicting Name)
        # -------------------------------------------------------------
        print("\n-------------------------------------------------------")
        print("TEST 4: Same Register Number with Conflicting Name")
        print("-------------------------------------------------------")
        cert4_id = uuid.uuid4().hex
        conflict_img = np.full((600, 400, 3), (250, 240, 230), dtype=np.uint8)
        cv2.rectangle(conflict_img, (20, 20), (380, 100), (20, 40, 120), -1)
        cv2.putText(conflict_img, "OXFORD UNIVERSITY", (30, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(conflict_img, "Degree of Science", (30, 160), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (10, 10, 10), 1)
        cv2.putText(conflict_img, "Robert Downey Jr", (30, 220), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 20, 20), 2)
        cv2.putText(conflict_img, f"Ref {run_nonce}_conf", (40, 280), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (50, 50, 50), 1)
        _, enc_conf = cv2.imencode(".jpg", conflict_img)
        cert4_bytes = enc_conf.tobytes()
        cert4_storage_path = await storage.save_bytes(cert4_bytes, f"stolen_reg_{run_nonce}.jpg")
        cert4 = Certificate(
            id=cert4_id,
            organization_id=user.organization_id,
            owner_id=user_b.id,
            original_filename="Stolen_Reg_Cert.jpg",
            storage_path=cert4_storage_path,
            file_type="jpg",
            file_size_bytes=len(cert4_bytes),
            sha256_hash=hashlib.sha256(cert4_bytes).hexdigest(),
        )
        db.add(cert4)
        ocr4 = OCRData(
            id=uuid.uuid4().hex,
            certificate_id=cert4_id,
            register_number=orig_ocr.register_number,
            student_name="Robert Downey Jr",  # completely different name!
        )
        db.add(ocr4)
        job4 = VerificationJob(
            id=uuid.uuid4().hex,
            organization_id=user.organization_id,
            certificate_id=cert4_id,
            stage_states={},
        )
        db.add(job4)
        await db.commit()

        vr4 = await run_duplicate_detection(cert4_id, user=user_b, db=db)
        print(f"-> Test 4 Results:")
        print(f"   is_duplicate:                {vr4.is_duplicate}")
        print(f"   duplicate_type:              {vr4.duplicate_detail.get('duplicate_type')}")
        print(f"   duplicate_status:            {vr4.duplicate_detail.get('duplicate_status')}")
        print(f"   match_layer:                 {vr4.duplicate_detail.get('match_layer')}")
        print(f"   conflicting_fields:          {vr4.duplicate_detail.get('conflicting_fields')}")
        print(f"   duplicate_match_reason:\n     \"{vr4.duplicate_match_reason}\"")
        assert vr4.is_duplicate is True
        assert vr4.duplicate_detail.get("duplicate_status") == "CERTIFICATE_CONFLICT"

        # -------------------------------------------------------------
        # TEST 5: Completely Different Certificate (No duplicate)
        # -------------------------------------------------------------
        print("\n-------------------------------------------------------")
        print("TEST 5: Completely Different Certificate (No match)")
        print("-------------------------------------------------------")
        diff_img = np.full((600, 400, 3), (220, 240, 220), dtype=np.uint8)
        cv2.circle(diff_img, (200, 300), 90, (40, 140, 40), -1)
        cv2.putText(diff_img, "UNIQUE CERTIFICATE", (40, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (20, 40, 20), 2)
        cv2.putText(diff_img, f"Serial: {run_nonce}", (40, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
        _, enc_diff = cv2.imencode(".jpg", diff_img)
        diff_bytes = enc_diff.tobytes()
        diff_hash = hashlib.sha256(diff_bytes).hexdigest()
        diff_path = await storage.save_bytes(diff_bytes, f"unique_cert_{run_nonce}.jpg")

        cert5_id = uuid.uuid4().hex
        cert5 = Certificate(
            id=cert5_id,
            organization_id=user.organization_id,
            owner_id=user.id,
            original_filename="Unique_Independent_Cert.jpg",
            storage_path=diff_path,
            file_type="jpg",
            file_size_bytes=len(diff_bytes),
            sha256_hash=diff_hash,
        )
        db.add(cert5)
        ocr5 = OCRData(
            id=uuid.uuid4().hex,
            certificate_id=cert5_id,
            register_number="UNIQUE-999-XYZ",
            certificate_number="CERT-UNIQUE-888",
            student_name="Arthur Pendelton",
        )
        db.add(ocr5)
        job5 = VerificationJob(
            id=uuid.uuid4().hex,
            organization_id=user.organization_id,
            certificate_id=cert5_id,
            stage_states={},
        )
        db.add(job5)
        await db.commit()

        vr5 = await run_duplicate_detection(cert5_id, user=user, db=db)
        print(f"-> Test 5 Results:")
        print(f"   is_duplicate:                {vr5.is_duplicate}")
        print(f"   duplicate_match_reason:\n     \"{vr5.duplicate_match_reason}\"")
        assert vr5.is_duplicate is False

        print("\n=======================================================")
        print("SUMMARY OF MATCH REASONS ACROSS ALL SCENARIOS")
        print("=======================================================")
        scenarios = [
            ("Same File Uploaded Twice", vr1.duplicate_match_reason),
            ("Re-saved / Re-scanned File", vr2.duplicate_match_reason),
            ("Same Register No + Fuzzy Name", vr3.duplicate_match_reason),
            ("Same Register No + Name Conflict", vr4.duplicate_match_reason),
            ("Different Certificate", vr5.duplicate_match_reason),
        ]
        for name, reason in scenarios:
            print(f"• {name:<35}: {reason}")

        print("\nALL MODULE 4 DUPLICATE TESTS COMPLETED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(main())
