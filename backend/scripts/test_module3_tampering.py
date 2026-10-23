"""
Test script for MODULE 3: Tampering & Forgery Detection stage.
Validates:
1. Running tampering detection on original certificate (Keerthana_12th_Marksheet.pdf)
2. Creating an edited/tampered copy (altering a digit/marks region)
3. Running tampering detection on the edited copy and showing that scores differ
4. Verifying that the ELA heatmap is generated, stored, and served via GET /{id}/ela-heatmap with auth
5. Printing all resulting database fields and stage_states.
"""
import asyncio
import os
import sys
import uuid
import cv2
import numpy as np

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, backend_dir)

from sqlalchemy import select
from app.db.database import AsyncSessionLocal, init_db
from app.models.models import Certificate, User, OCRData, VerificationResult, VerificationJob
from app.api.verification import run_tampering_detection, get_ela_heatmap
from app.services.storage_service import get_storage_backend
from app.services.image_preprocessing import load_image_as_array
from app.core.config import settings


async def main():
    await init_db()
    async with AsyncSessionLocal() as db:
        storage = get_storage_backend()

        print("\n=======================================================")
        print("1. TEST ORIGINAL CERTIFICATE (Keerthana_12th_Marksheet.pdf)")
        print("=======================================================")
        orig_cert_id = "b4d835cd6e81412692317d3854a156f5"
        cert_res = await db.execute(select(Certificate).where(Certificate.id == orig_cert_id))
        orig_cert = cert_res.scalar_one_or_none()
        assert orig_cert is not None, f"Original certificate {orig_cert_id} not found!"

        user_res = await db.execute(select(User).where(User.id == orig_cert.owner_id))
        user = user_res.scalar_one_or_none()
        assert user is not None, f"User {orig_cert.owner_id} not found!"

        # Run tampering detection on original certificate
        orig_vr = await run_tampering_detection(orig_cert_id, user=user, db=db)
        print(f"-> Original Document Tampering Analysis Results:")
        print(f"   tampering_score:      {orig_vr.tampering_score:.2f} / 100")
        print(f"   tampering_risk_level: {orig_vr.tampering_risk_level}")
        print(f"   tampering_confidence: {orig_vr.tampering_confidence:.1f}%")
        print(f"   ela_heatmap_path:     {orig_vr.ela_heatmap_path}")
        print(f"   tampering_flags:      {orig_vr.tampering_flags}")
        print(f"   per-check breakdown:  {list(orig_vr.tampering_detail.get('checks', {}).keys())}")

        # Check stage_states in job
        job_res = await db.execute(
            select(VerificationJob).where(VerificationJob.certificate_id == orig_cert_id).order_by(VerificationJob.id.desc())
        )
        job = job_res.scalars().first()
        print(f"   stage_states['tampering']:\n     {job.stage_states.get('tampering') if job else 'No job'}")

        print("\n=======================================================")
        print("2. CREATE DELIBERATELY EDITED COPY (Altering Digits/Region)")
        print("=======================================================")
        # Load the original file bytes
        orig_bytes = await storage.read(orig_cert.storage_path)
        orig_img = load_image_as_array(orig_bytes, orig_cert.file_type)

        # Clone and deliberately edit a text/marks region (change digits/splice a modified block)
        edited_img = orig_img.copy()
        h, w = edited_img.shape[:2]

        # Draw a whiteout box over a number and insert spliced/tampered digits with different compression/noise
        y1, y2 = int(h * 0.45), int(h * 0.45) + 60
        x1, x2 = int(w * 0.50), int(w * 0.50) + 180
        cv2.rectangle(edited_img, (x1, y1), (x2, y2), (255, 255, 255), -1)
        # Put altered text with high contrast stroke
        cv2.putText(
            edited_img, "99.8%", (x1 + 10, y1 + 45),
            cv2.FONT_HERSHEY_DUPLEX, 1.4, (10, 10, 10), 3, cv2.LINE_AA
        )
        # Also copy-paste another patch to create clone & noise discrepancy
        patch_src = orig_img[int(h * 0.2):int(h * 0.2) + 70, int(w * 0.2):int(w * 0.2) + 120]
        edited_img[int(h * 0.7):int(h * 0.7) + 70, int(w * 0.7):int(w * 0.7) + 120] = patch_src

        # Encode as JPEG with recompression to introduce localized compression boundary
        success, encoded_jpg = cv2.imencode(".jpg", edited_img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        assert success, "Failed encoding edited image"
        edited_bytes = encoded_jpg.tobytes()

        # Save to storage
        edited_storage_path = await storage.save_bytes(edited_bytes, "tampered_marksheet_sample.jpg")

        # Create certificate record for the edited document
        tampered_cert_id = uuid.uuid4().hex
        tampered_cert = Certificate(
            id=tampered_cert_id,
            organization_id=user.organization_id,
            owner_id=user.id,
            original_filename="Keerthana_12th_Marksheet_EDITED.jpg",
            storage_path=edited_storage_path,
            file_type="jpg",
            file_size_bytes=len(edited_bytes),
            sha256_hash="1" * 64,
        )
        db.add(tampered_cert)

        # Create verification job
        tampered_job = VerificationJob(
            id=uuid.uuid4().hex,
            organization_id=user.organization_id,
            certificate_id=tampered_cert_id,
            stage_states={},
        )
        db.add(tampered_job)
        await db.commit()

        print(f"-> Created tampered certificate record ID: {tampered_cert_id}")

        print("\n=======================================================")
        print("3. RUN TAMPERING DETECTION ON EDITED COPY")
        print("=======================================================")
        tampered_vr = await run_tampering_detection(tampered_cert_id, user=user, db=db)
        print(f"-> Tampered Document Results:")
        print(f"   tampering_score:      {tampered_vr.tampering_score:.2f} / 100")
        print(f"   tampering_risk_level: {tampered_vr.tampering_risk_level}")
        print(f"   tampering_confidence: {tampered_vr.tampering_confidence:.1f}%")
        print(f"   ela_heatmap_path:     {tampered_vr.ela_heatmap_path}")
        print(f"   tampering_flags:      {tampered_vr.tampering_flags}")

        job_res_tamp = await db.execute(
            select(VerificationJob).where(VerificationJob.certificate_id == tampered_cert_id).order_by(VerificationJob.id.desc())
        )
        job_tamp = job_res_tamp.scalars().first()
        print(f"   stage_states['tampering']:\n     {job_tamp.stage_states.get('tampering')}")

        print("\n=======================================================")
        print("4. COMPARISON OF ORIGINAL VS EDITED SCORES")
        print("=======================================================")
        diff = tampered_vr.tampering_score - orig_vr.tampering_score
        print(f"Original Certificate Score:  {orig_vr.tampering_score:.2f}  ({orig_vr.tampering_risk_level})")
        print(f"Edited Certificate Score:    {tampered_vr.tampering_score:.2f}  ({tampered_vr.tampering_risk_level})")
        print(f"Score Difference (Delta):    +{diff:.2f}")

        print("\n--- Per-Check Score Comparison ---")
        orig_checks = orig_vr.tampering_detail.get("checks", {})
        tamp_checks = tampered_vr.tampering_detail.get("checks", {})
        all_check_names = sorted(set(orig_checks.keys()) | set(tamp_checks.keys()))
        print(f"{'Check Name':<28} | {'Original Score':<15} | {'Edited Score':<15} | {'Difference'}")
        print("-" * 75)
        for name in all_check_names:
            s_orig = orig_checks.get(name, {}).get("score", 0.0)
            s_tamp = tamp_checks.get(name, {}).get("score", 0.0)
            d = s_tamp - s_orig
            print(f"{name:<28} | {s_orig:<15.2f} | {s_tamp:<15.2f} | {'+' if d>=0 else ''}{d:.2f}")

        assert tampered_vr.tampering_score > orig_vr.tampering_score, "Tampered score should be higher than original!"
        print("\n[PASS] The edited certificate exhibits higher tampering scores!")

        print("\n=======================================================")
        print("5. VERIFY SERVING HEATMAP VIA ENDPOINT WITH AUTH")
        print("=======================================================")
        # Test endpoint get_ela_heatmap directly
        heatmap_response = await get_ela_heatmap(orig_cert_id, user=user, db=db)
        assert heatmap_response.status_code == 200, f"Expected 200, got {heatmap_response.status_code}"
        assert heatmap_response.media_type == "image/png", f"Expected image/png, got {heatmap_response.media_type}"
        print(f"-> Successfully served ELA Heatmap via API! (media_type: {heatmap_response.media_type})")

        print("\nALL MODULE 3 TAMPERING TESTS COMPLETED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(main())
