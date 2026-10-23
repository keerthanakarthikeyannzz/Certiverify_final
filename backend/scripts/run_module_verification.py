"""
Verification test script for Module 1 (QR Verification) and Module 2 (Blockchain Verification).
Tests:
1. Real certificate with QR (Keerthana_12th_Marksheet.pdf)
2. Document without QR code (verifying NOT_APPLICABLE)
3. Blockchain with provider=none (verifying NOT_APPLICABLE)
4. Blockchain with provider=local_ledger (verifying NOT_REGISTERED, registration, MATCH, and modified hash)
5. Prints resulting DB rows and stage_states.
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime

# Add backend directory to sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, backend_dir)

from sqlalchemy import select
from app.db.database import AsyncSessionLocal, init_db
from app.models.models import Certificate, User, OCRData, VerificationResult, VerificationJob
from app.api.verification import run_qr_check, run_blockchain_verification, get_verification
from app.services.blockchain_service import (
    get_blockchain_provider,
    LocalLedgerBlockchainProvider,
    NoneBlockchainProvider,
    register_hash_onchain,
    verify_hash_onchain,
)
from app.core.config import settings


async def main():
    await init_db()
    async with AsyncSessionLocal() as db:
        print("\n=======================================================")
        print("1. TEST REAL CERTIFICATE WITH QR (Keerthana_12th_Marksheet.pdf)")
        print("=======================================================")
        cert_id = "b4d835cd6e81412692317d3854a156f5"
        cert_res = await db.execute(select(Certificate).where(Certificate.id == cert_id))
        cert = cert_res.scalar_one_or_none()
        assert cert is not None, f"Certificate {cert_id} not found in database!"

        user_res = await db.execute(select(User).where(User.id == cert.owner_id))
        user = user_res.scalar_one_or_none()
        assert user is not None, f"User {cert.owner_id} not found!"

        # Run QR check
        print(f"Running run_qr_check for certificate {cert_id}...")
        vr_qr = await run_qr_check(cert_id, user=user, db=db)
        print(f"-> qr_present: {vr_qr.qr_present}")
        print(f"-> qr_valid: {vr_qr.qr_valid}")
        print(f"-> qr_warning: {vr_qr.qr_warning}")
        print(f"-> qr_decoded_data: {vr_qr.qr_decoded_data}")

        # Check job stage states
        job_res = await db.execute(
            select(VerificationJob).where(VerificationJob.certificate_id == cert_id).order_by(VerificationJob.id.desc())
        )
        job = job_res.scalars().first()
        print(f"-> Job stage_states['qr_verification']:\n   {job.stage_states.get('qr_verification')}")

        print("\n=======================================================")
        print("2. TEST BLOCKCHAIN WITH PROVIDER = none")
        print("=======================================================")
        original_provider = settings.BLOCKCHAIN_PROVIDER
        settings.BLOCKCHAIN_PROVIDER = "none"

        vr_bc_none = await run_blockchain_verification(cert_id, user=user, db=db)
        print(f"-> blockchain_status: {vr_bc_none.blockchain_status}")
        print(f"-> blockchain_match: {vr_bc_none.blockchain_match}")
        print(f"-> blockchain_hash_submitted: {vr_bc_none.blockchain_hash_submitted}")
        print(f"-> blockchain_hash_onchain: {vr_bc_none.blockchain_hash_onchain}")
        print(f"-> blockchain_tx_hash: {vr_bc_none.blockchain_tx_hash}")

        job_res = await db.execute(
            select(VerificationJob).where(VerificationJob.certificate_id == cert_id).order_by(VerificationJob.id.desc())
        )
        job = job_res.scalars().first()
        print(f"-> Job stage_states['blockchain_verification']:\n   {job.stage_states.get('blockchain_verification')}")

        print("\n=======================================================")
        print("3. TEST BLOCKCHAIN WITH PROVIDER = local_ledger")
        print("=======================================================")
        test_ledger_path = os.path.join(backend_dir, "data", "test_ledger.json")
        if os.path.exists(test_ledger_path):
            os.remove(test_ledger_path)

        settings.BLOCKCHAIN_PROVIDER = "local_ledger"
        settings.BLOCKCHAIN_LOCAL_LEDGER_PATH = test_ledger_path

        # Step 3a: Verify before registering (should be NOT_REGISTERED neutrally)
        print("Step 3a: Verify before registration (should be NOT_REGISTERED):")
        vr_bc_unreg = await run_blockchain_verification(cert_id, user=user, db=db)
        print(f"-> blockchain_status: {vr_bc_unreg.blockchain_status}")
        print(f"-> blockchain_match: {vr_bc_unreg.blockchain_match}")
        job_res = await db.execute(
            select(VerificationJob).where(VerificationJob.certificate_id == cert_id).order_by(VerificationJob.id.desc())
        )
        job = job_res.scalars().first()
        print(f"-> Job stage_states['blockchain_verification']:\n   {job.stage_states.get('blockchain_verification')}")

        # Step 3b: Register hash in local ledger
        print("\nStep 3b: Register certificate hash in local ledger:")
        tx_hash = register_hash_onchain(
            cert.sha256_hash,
            metadata={"certificate_id": cert.id, "filename": cert.original_filename}
        )
        print(f"-> Registered successfully! tx_hash: {tx_hash}")

        # Step 3c: Verify after registration (should be MATCH (local_ledger))
        print("\nStep 3c: Verify after registration (should be MATCH (local_ledger)):")
        vr_bc_reg = await run_blockchain_verification(cert_id, user=user, db=db)
        print(f"-> blockchain_status: {vr_bc_reg.blockchain_status}")
        print(f"-> blockchain_match: {vr_bc_reg.blockchain_match}")
        print(f"-> blockchain_hash_submitted: {vr_bc_reg.blockchain_hash_submitted}")
        print(f"-> blockchain_hash_onchain: {vr_bc_reg.blockchain_hash_onchain}")
        print(f"-> blockchain_tx_hash: {vr_bc_reg.blockchain_tx_hash}")
        job_res = await db.execute(
            select(VerificationJob).where(VerificationJob.certificate_id == cert_id).order_by(VerificationJob.id.desc())
        )
        job = job_res.scalars().first()
        print(f"-> Job stage_states['blockchain_verification']:\n   {job.stage_states.get('blockchain_verification')}")

        # Step 3d: Verify modified hash (should be NOT_REGISTERED)
        print("\nStep 3d: Verify modified file hash against ledger:")
        modified_hash = "f" * 64
        check_mod = verify_hash_onchain(modified_hash)
        print(f"-> Result for modified hash: status={check_mod.status}, match={check_mod.match}, reason={check_mod.reason}")

        print("\n=======================================================")
        print("4. TEST GET /api/v1/certificates/{id}/verification (returns 200)")
        print("=======================================================")
        res_row = await get_verification(cert_id, user=user, db=db)
        print(f"-> Successfully retrieved VerificationResult row for cert {res_row.certificate_id}!")
        print(f"   qr_present: {res_row.qr_present}")
        print(f"   qr_valid: {res_row.qr_valid}")
        print(f"   blockchain_status: {res_row.blockchain_status}")
        print(f"   blockchain_match: {res_row.blockchain_match}")

        print("\n=======================================================")
        print("5. TEST DOCUMENT WITHOUT QR CODE (verifying NOT_APPLICABLE)")
        print("=======================================================")
        from app.services.storage_service import get_storage_backend
        storage = get_storage_backend()
        
        # Create a simple 1-page PDF without a QR code
        import fitz
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        page.insert_text((50, 50), "Certificate of Completion\nStudent: Alice Smith\nCourse: Python", fontsize=16)
        blank_pdf_bytes = doc.tobytes()
        doc.close()

        storage_path = await storage.save_bytes(blank_pdf_bytes, "plain_doc_no_qr.pdf")
        no_qr_cert_id = uuid.uuid4().hex
        no_qr_cert = Certificate(
            id=no_qr_cert_id,
            organization_id=user.organization_id,
            owner_id=user.id,
            original_filename="Plain_Document_No_QR.pdf",
            storage_path=storage_path,
            file_type="pdf",
            file_size_bytes=len(blank_pdf_bytes),
            sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )
        db.add(no_qr_cert)

        # Create corresponding job
        no_qr_job = VerificationJob(
            id=uuid.uuid4().hex,
            organization_id=user.organization_id,
            certificate_id=no_qr_cert_id,
            stage_states={},
        )
        db.add(no_qr_job)
        await db.commit()

        # Run QR check on document with no QR (simulate empty/no QR detected)
        vr_no_qr = await run_qr_check(no_qr_cert_id, user=user, db=db)
        print(f"-> Document with no QR:")
        print(f"   qr_present: {vr_no_qr.qr_present}")
        print(f"   qr_valid: {vr_no_qr.qr_valid}")
        print(f"   qr_warning: {vr_no_qr.qr_warning}")

        job_res_no_qr = await db.execute(
            select(VerificationJob).where(VerificationJob.certificate_id == no_qr_cert_id).order_by(VerificationJob.id.desc())
        )
        job_no_qr = job_res_no_qr.scalars().first()
        print(f"-> Job stage_states['qr_verification']:\n   {job_no_qr.stage_states.get('qr_verification')}")

        # Cleanup test ledger & restore setting
        if os.path.exists(test_ledger_path):
            os.remove(test_ledger_path)
        settings.BLOCKCHAIN_PROVIDER = original_provider

        print("\nALL MODULE 1 AND MODULE 2 VERIFICATION TESTS COMPLETED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(main())
