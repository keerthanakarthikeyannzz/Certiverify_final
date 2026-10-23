"""
Verification script for MODULE 5: AI Fraud Analysis (fraud_analysis)
Tests:
1. Gathers normalised risk signals for:
   a) Clean original document (Keerthana_12th_Marksheet.pdf)
   b) Edited/tampered document from Module 3 (Keerthana_12th_Marksheet_EDITED.jpg)
2. Runs run_fraud_analysis to populate fraud_analysis table
3. Calls get_fraud_analysis to verify GET /fraud-analysis endpoint
4. Displays side-by-side comparison of signals, weights, contributions, and resulting probability
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
from app.models.models import Certificate, User, OCRData, VerificationResult, VerificationJob, FraudAnalysis
from app.api.fraud import run_fraud_analysis, get_fraud_analysis
from app.api.verification import run_tampering_detection, run_duplicate_detection
from app.services.storage_service import get_storage_backend
from app.services.image_preprocessing import load_image_as_array


async def main():
    await init_db()
    async with AsyncSessionLocal() as db:
        storage = get_storage_backend()

        print("\n=======================================================")
        print("MODULE 5: AI FRAUD ANALYSIS TEST SUITE")
        print("=======================================================")

        # 1. Base clean certificate
        orig_cert_id = "b4d835cd6e81412692317d3854a156f5"
        cert_res = await db.execute(select(Certificate).where(Certificate.id == orig_cert_id))
        orig_cert = cert_res.scalar_one_or_none()
        assert orig_cert is not None, f"Original certificate {orig_cert_id} not found!"

        user_res = await db.execute(select(User).where(User.id == orig_cert.owner_id))
        user = user_res.scalar_one_or_none()
        assert user is not None, f"User {orig_cert.owner_id} not found!"

        # Ensure OCR data exists
        ocr_res = await db.execute(select(OCRData).where(OCRData.certificate_id == orig_cert_id))
        orig_ocr = ocr_res.scalar_one_or_none()
        if not orig_ocr:
            orig_ocr = OCRData(
                id=uuid.uuid4().hex,
                certificate_id=orig_cert_id,
                student_name="Keerthana K",
                register_number="2212255949",
                certificate_number="HSC-2023-091823",
                ocr_accuracy=0.96,
                field_confidences={"student_name": 0.98, "register_number": 0.95},
            )
            db.add(orig_ocr)
            await db.commit()

        # Run tampering and duplicate detection on clean cert if missing
        clean_vr_res = await db.execute(select(VerificationResult).where(VerificationResult.certificate_id == orig_cert_id))
        clean_vr = clean_vr_res.scalar_one_or_none()
        if not clean_vr or clean_vr.tampering_score is None:
            clean_vr = await run_tampering_detection(orig_cert_id, user=user, db=db)
        if clean_vr.is_duplicate is None:
            clean_vr = await run_duplicate_detection(orig_cert_id, user=user, db=db)

        # 2. Setup or create edited/tampered copy from Module 3
        edited_cert_res = await db.execute(
            select(Certificate)
            .where(Certificate.original_filename == "Keerthana_12th_Marksheet_EDITED.jpg")
            .order_by(Certificate.uploaded_at.desc())
        )
        edited_cert = edited_cert_res.scalars().first()

        orig_bytes = await storage.read(orig_cert.storage_path)
        orig_img = load_image_as_array(orig_bytes, orig_cert.file_type)

        if not edited_cert:
            # Create edited image with spliced text and noise discrepancy
            edited_img = orig_img.copy()
            h, w = edited_img.shape[:2]
            x1, y1 = int(w * 0.45), int(h * 0.50)
            x2, y2 = int(w * 0.75), int(h * 0.55)

            # Inpaint / white-out section
            cv2.rectangle(edited_img, (x1, y1), (x2, y2), (255, 255, 255), -1)
            # Add synthetic forged marks text
            cv2.putText(
                edited_img, "MATHEMATICS: 199/200", (x1 + 5, y1 + 35),
                cv2.FONT_HERSHEY_DUPLEX, 0.9, (10, 10, 10), 2, cv2.LINE_AA
            )
            # Paste cloned patch
            patch = orig_img[int(h * 0.2):int(h * 0.2) + 70, int(w * 0.2):int(w * 0.2) + 120]
            edited_img[int(h * 0.7):int(h * 0.7) + 70, int(w * 0.7):int(w * 0.7) + 120] = patch

            _, enc_edit = cv2.imencode(".jpg", edited_img, [cv2.IMWRITE_JPEG_QUALITY, 75])
            edit_bytes = enc_edit.tobytes()
            edit_path = await storage.save_bytes(edit_bytes, "marksheet_module3_edited.jpg")

            edited_cert_id = uuid.uuid4().hex
            edited_cert = Certificate(
                id=edited_cert_id,
                organization_id=user.organization_id,
                owner_id=user.id,
                original_filename="Keerthana_12th_Marksheet_EDITED.jpg",
                storage_path=edit_path,
                file_type="jpg",
                file_size_bytes=len(edit_bytes),
                sha256_hash=hashlib.sha256(edit_bytes).hexdigest(),
            )
            db.add(edited_cert)
            edit_job = VerificationJob(
                id=uuid.uuid4().hex,
                organization_id=user.organization_id,
                certificate_id=edited_cert_id,
                stage_states={},
            )
            db.add(edit_job)
            await db.commit()

        # Run tampering and duplicate on edited document
        edited_vr = await run_tampering_detection(edited_cert.id, user=user, db=db)
        edited_vr = await run_duplicate_detection(edited_cert.id, user=user, db=db)

        # =====================================================================
        # 1. RUN FRAUD ANALYSIS ON CLEAN DOCUMENT
        # =====================================================================
        print("\n-------------------------------------------------------")
        print("1. RUN FRAUD ANALYSIS: CLEAN ORIGINAL DOCUMENT")
        print("-------------------------------------------------------")
        clean_fraud_post = await run_fraud_analysis(orig_cert_id, user=user, db=db)
        clean_fraud_get = await get_fraud_analysis(orig_cert_id, user=user, db=db)

        print(f"Document ID:        {orig_cert.id}")
        print(f"File Name:          {orig_cert.original_filename}")
        print(f"Fraud Probability:  {clean_fraud_get.fraud_probability:.4f} ({clean_fraud_get.fraud_probability * 100:.1f}%)")
        print(f"Risk Level:         {clean_fraud_get.risk_level}")
        print(f"Overrides Applied:  {clean_fraud_get.critical_overrides_applied or 'None'}")

        print("\nSignal Contributions for Clean Document:")
        print(f"{'Signal':<25} {'Active':<8} {'Weight':<10} {'Risk':<10} {'Contrib':<10} {'Status':<12}")
        print("-" * 75)
        for sc in clean_fraud_get.signal_contributions:
            act_str = "YES" if sc.is_active else "NO (omit)"
            risk_str = f"{sc.risk:.3f}" if sc.risk is not None else "N/A"
            eff_w_str = f"{sc.effective_weight:.3f}"
            contrib_str = f"{sc.contribution:.4f}"
            print(f"{sc.signal:<25} {act_str:<8} {eff_w_str:<10} {risk_str:<10} {contrib_str:<10} {sc.status:<12}")

        # Assertions for clean document
        assert clean_fraud_get.fraud_probability < 0.25, f"Expected clean cert fraud prob < 0.25, got {clean_fraud_get.fraud_probability}"
        assert clean_fraud_get.risk_level == "LOW"

        # =====================================================================
        # 2. RUN FRAUD ANALYSIS ON EDITED DOCUMENT (MODULE 3 COPY)
        # =====================================================================
        print("\n-------------------------------------------------------")
        print("2. RUN FRAUD ANALYSIS: EDITED / TAMPERED COPY (MODULE 3)")
        print("-------------------------------------------------------")
        edited_fraud_post = await run_fraud_analysis(edited_cert.id, user=user, db=db)
        edited_fraud_get = await get_fraud_analysis(edited_cert.id, user=user, db=db)

        print(f"Document ID:        {edited_cert.id}")
        print(f"File Name:          {edited_cert.original_filename}")
        print(f"Fraud Probability:  {edited_fraud_get.fraud_probability:.4f} ({edited_fraud_get.fraud_probability * 100:.1f}%)")
        print(f"Risk Level:         {edited_fraud_get.risk_level}")
        print(f"Overrides Applied:  {edited_fraud_get.critical_overrides_applied or 'None'}")

        print("\nSignal Contributions for Edited Document:")
        print(f"{'Signal':<25} {'Active':<8} {'Weight':<10} {'Risk':<10} {'Contrib':<10} {'Status':<12}")
        print("-" * 75)
        for sc in edited_fraud_get.signal_contributions:
            act_str = "YES" if sc.is_active else "NO (omit)"
            risk_str = f"{sc.risk:.3f}" if sc.risk is not None else "N/A"
            eff_w_str = f"{sc.effective_weight:.3f}"
            contrib_str = f"{sc.contribution:.4f}"
            print(f"{sc.signal:<25} {act_str:<8} {eff_w_str:<10} {risk_str:<10} {contrib_str:<10} {sc.status:<12}")

        # Assertions for edited document
        assert edited_fraud_get.fraud_probability > clean_fraud_get.fraud_probability
        assert edited_fraud_get.risk_level in ("HIGH", "VERY_HIGH", "MODERATE")

        # =====================================================================
        # 3. SIDE-BY-SIDE SUMMARY
        # =====================================================================
        print("\n=======================================================")
        print("3. SIDE-BY-SIDE COMPARISON: CLEAN VS EDITED DOCUMENT")
        print("=======================================================")
        print(f"{'Metric':<30} {'Clean Document':<22} {'Edited Document':<22}")
        print("-" * 74)
        print(f"{'Fraud Probability':<30} {clean_fraud_get.fraud_probability * 100:.1f}%{'':<17} {edited_fraud_get.fraud_probability * 100:.1f}%")
        print(f"{'Risk Level':<30} {clean_fraud_get.risk_level:<22} {edited_fraud_get.risk_level:<22}")
        print(f"{'Tampering Score':<30} {clean_vr.tampering_score:.1f}/100{'':<13} {edited_vr.tampering_score:.1f}/100")
        print(f"{'Tampering Risk':<30} {clean_vr.tampering_risk_level:<22} {edited_vr.tampering_risk_level:<22}")
        print(f"{'Active Signals':<30} {len(clean_fraud_get.factor_risks)} signals{'':<13} {len(edited_fraud_get.factor_risks)} signals")

        # Verify database persistence
        db_clean = (await db.execute(select(FraudAnalysis).where(FraudAnalysis.certificate_id == orig_cert.id))).scalar_one()
        db_edit = (await db.execute(select(FraudAnalysis).where(FraudAnalysis.certificate_id == edited_cert.id))).scalar_one()
        assert db_clean.fraud_probability == clean_fraud_get.fraud_probability
        assert db_edit.fraud_probability == edited_fraud_get.fraud_probability
        print("\nDatabase persistence confirmed for both fraud_analysis rows!")

        print("\nALL MODULE 5 AI FRAUD ANALYSIS TESTS COMPLETED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(main())
