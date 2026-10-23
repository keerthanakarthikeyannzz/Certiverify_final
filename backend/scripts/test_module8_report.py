"""
Verification script for MODULE 8: PDF Report Generation stage (report).

Test workflow:
1. Authenticates against the FastAPI backend.
2. Identifies or runs pipeline for test certificate.
3. Generates the PDF verification report via POST /api/v1/certificates/{id}/generate-report.
4. Confirms verification_reports row exists with verification_id, pdf_path, digital_signature.
5. Downloads the generated PDF via GET /api/v1/certificates/{id}/download-report.
6. Verifies the cryptographic HMAC-SHA256 signature -> confirmed VALID.
7. Alters the PDF file on disk by 1 byte (simulating tampering).
8. Re-verifies signature on the altered PDF -> confirmed INVALID / TAMPERED.
9. Restores the untampered PDF and confirms verification passes again.
10. Lists all generated reports via GET /api/v1/reports -> confirmed included in list.
"""
import asyncio
import os
import shutil
import sys

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from app.main import app
from app.db.database import AsyncSessionLocal, init_db
from app.models.models import Certificate, User, VerificationReport, VerificationResult, FinalPrediction
from app.services.report_service import verify_report_signature
from app.core.security import create_access_token


async def main():
    print("=" * 70)
    print("MODULE 8: PDF REPORT GENERATION & DIGITAL SIGNATURE TEST")
    print("=" * 70)

    await init_db()

    async with AsyncSessionLocal() as db:
        # 1. Fetch test user and certificate
        user_res = await db.execute(select(User).limit(1))
        user = user_res.scalar_one_or_none()
        assert user is not None, "No test user found in DB"

        cert_res = await db.execute(
            select(Certificate)
            .where(Certificate.owner_id == user.id)
            .order_by(Certificate.uploaded_at.desc())
        )
        cert = cert_res.scalars().first()
        if not cert:
            all_certs = (await db.execute(select(Certificate))).scalars().all()
            assert all_certs, "No certificates in database"
            cert = all_certs[0]

        print(f"[*] User: {user.email} (Org: {user.organization_id})")
        print(f"[*] Certificate ID: {cert.id} ({cert.original_filename})")

        # Ensure pipeline prerequisites exist (verification_results & final_predictions)
        vr_res = await db.execute(select(VerificationResult).where(VerificationResult.certificate_id == cert.id))
        vr = vr_res.scalar_one_or_none()
        pred_res = await db.execute(select(FinalPrediction).where(FinalPrediction.certificate_id == cert.id))
        pred = pred_res.scalar_one_or_none()

        if not vr or not pred:
            print("[*] Prerequisites missing; running verification and prediction first...")
            from app.api.verification import run_tampering_detection, run_qr_check, run_blockchain_verification, run_duplicate_detection
            from app.api.fraud import run_fraud_analysis
            from app.api.trust_score import run_trust_score
            from app.api.prediction import run_prediction

            await run_qr_check(cert.id, user, db)
            await run_blockchain_verification(cert.id, user, db)
            await run_tampering_detection(cert.id, user, db)
            await run_duplicate_detection(cert.id, user, db)
            await run_fraud_analysis(cert.id, user, db)
            await run_trust_score(cert.id, user, db)
            await run_prediction(cert.id, user, db)

    # Create auth token
    role_val = user.role.value if hasattr(user.role, "value") else str(user.role)
    token = create_access_token(user.id, {"email": user.email, "role": role_val})
    headers = {"Authorization": f"Bearer {token}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Step 1: POST generate report
        print("\n[Step 1] Calling POST /api/v1/certificates/{id}/generate-report...")
        gen_res = await client.post(f"/api/v1/certificates/{cert.id}/generate-report", headers=headers)
        print(f"Status Code: {gen_res.status_code}")
        assert gen_res.status_code == 200, f"Generate report failed: {gen_res.text}"
        rep_data = gen_res.json()
        vid = rep_data["verification_id"]
        sig = rep_data["digital_signature"]
        pdf_path = rep_data["pdf_path"]
        print(f"Generated Verification ID: {vid}")
        print(f"Digital Signature (HMAC-SHA256): {sig}")
        print(f"PDF File Path on disk: {pdf_path}")
        assert vid.startswith("CV-"), f"Invalid verification ID format: {vid}"
        assert len(sig) == 64, f"Invalid signature length: {sig}"
        assert os.path.exists(pdf_path), f"PDF file does not exist on disk: {pdf_path}"

        # Step 2: Check database row
        print("\n[Step 2] Checking verification_reports table in DB...")
        async with AsyncSessionLocal() as db:
            row_res = await db.execute(select(VerificationReport).where(VerificationReport.certificate_id == cert.id))
            rep_row = row_res.scalar_one_or_none()
            assert rep_row is not None, "Report row not found in DB"
            assert rep_row.verification_id == vid
            assert rep_row.digital_signature == sig
            print(f"DB verification_reports row verified! ID: {rep_row.id}")

        # Step 3: GET /report metadata
        print("\n[Step 3] Calling GET /api/v1/certificates/{id}/report...")
        meta_res = await client.get(f"/api/v1/certificates/{cert.id}/report", headers=headers)
        assert meta_res.status_code == 200
        assert meta_res.json()["verification_id"] == vid
        print("GET /report returned correct metadata.")

        # Step 4: GET /download-report
        print("\n[Step 4] Downloading PDF via GET /api/v1/certificates/{id}/download-report...")
        dl_res = await client.get(f"/api/v1/certificates/{cert.id}/download-report", headers=headers)
        assert dl_res.status_code == 200
        assert dl_res.headers["content-type"] == "application/pdf"
        assert dl_res.content.startswith(b"%PDF-")
        print(f"Downloaded PDF size: {len(dl_res.content)} bytes (valid %PDF header)")

        # Step 5: Verify signature on untampered PDF
        print("\n[Step 5] Verifying digital signature on untampered PDF...")
        verify_api_res = await client.post(f"/api/v1/certificates/{cert.id}/verify-signature", headers=headers)
        assert verify_api_res.status_code == 200
        v_data = verify_api_res.json()
        print(f"API verify result: is_valid = {v_data['is_valid']}")
        assert v_data["is_valid"] is True, "Signature verification should pass for untampered PDF!"

        # Direct python verification
        py_valid = verify_report_signature(pdf_path, sig)
        assert py_valid is True
        print("Python direct verify_report_signature passed: True")

        # Step 6: Tamper test: alter PDF file
        print("\n[Step 6] Altering PDF file (tamper test)...")
        backup_path = pdf_path + ".bak"
        shutil.copy2(pdf_path, backup_path)
        try:
            with open(pdf_path, "r+b") as f:
                content = bytearray(f.read())
                # Flip byte near the end
                content[-20] = (content[-20] + 1) % 256
                f.seek(0)
                f.write(content)
            print("Modified 1 byte in the stored PDF file.")

            # Re-verify tampered PDF
            print("[Step 7] Verifying tampered PDF...")
            tamper_api_res = await client.post(f"/api/v1/certificates/{cert.id}/verify-signature", headers=headers)
            assert tamper_api_res.status_code == 200
            tamper_data = tamper_api_res.json()
            print(f"API verify result on altered PDF: is_valid = {tamper_data['is_valid']}")
            print(f"Detail: {tamper_data['detail']}")
            assert tamper_data["is_valid"] is False, "Signature verification MUST fail when PDF is altered!"

            py_tamper_valid = verify_report_signature(pdf_path, sig)
            assert py_tamper_valid is False
            print("Python direct verify_report_signature on altered PDF confirmed: False!")
        finally:
            # Restore original
            shutil.move(backup_path, pdf_path)
            print("Restored original untampered PDF.")

        # Re-verify restored PDF
        restore_api_res = await client.post(f"/api/v1/certificates/{cert.id}/verify-signature", headers=headers)
        assert restore_api_res.json()["is_valid"] is True
        print("Restored PDF re-verified successfully: True")

        # Step 8: GET /api/v1/reports
        print("\n[Step 8] Calling GET /api/v1/reports to test reports listing...")
        list_res = await client.get("/api/v1/reports", headers=headers)
        assert list_res.status_code == 200
        reports_list = list_res.json()
        print(f"Total reports in list: {len(reports_list)}")
        assert any(r["verification_id"] == vid for r in reports_list), "Generated report not in reports list!"
        print(f"Found report {vid} in reports list with filename: {reports_list[0]['certificate_filename']}")

        print("\n" + "=" * 70)
        print("ALL MODULE 8 PDF REPORT & TAMPERING TESTS PASSED!")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
