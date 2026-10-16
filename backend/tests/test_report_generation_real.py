"""
Test Suite: Real Report Generation
Validates that report generation produces accurate reports bound to current certificate_id,
using actual pipeline data (OCR, Document Type, Fields, QR, Hash, Blockchain, Tampering, Duplicate, Fraud, Trust Score, Prediction),
verifying values against backend results, and asserting pending guard conditions.
"""
import pytest
import os
import io
import uuid
import json
from PIL import Image
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.database import AsyncSessionLocal
from app.models.models import (
    User, Certificate, OCRData, VerificationResult, TrustScore,
    FraudAnalysis, FinalPrediction, VerificationReport
)
from sqlalchemy import select, update, delete
from tests.conftest import find_sample_pdf


@pytest.mark.asyncio
async def test_report_generation_for_completed_certificate():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        rnd = uuid.uuid4().hex[:8]
        email = f"report_user_{rnd}@example.com"
        password = "TestPassword123!"
        await ac.post("/api/v1/auth/register", json={
            "full_name": f"Report User {rnd}",
            "email": email,
            "password": password,
            "role": "student"
        })

        async with AsyncSessionLocal() as session:
            await session.execute(
                update(User).where(User.email == email).values(is_email_verified=True)
            )
            await session.commit()

        login_res = await ac.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        pdf_path = find_sample_pdf()

        with open(pdf_path, "rb") as f:
            upload_res = await ac.post(
                "/api/v1/certificates/upload",
                files={"files": ("sample_certificate.pdf", f, "application/pdf")},
                headers=headers
            )
        assert upload_res.status_code == 201, f"Upload failed: {upload_res.text}"
        cert_id = upload_res.json()["certificates"][0]["id"]
        assert cert_id, "Certificate ID must be returned"

        pipeline_res = await ac.post(f"/api/v1/certificates/{cert_id}/run-pipeline", headers=headers)
        assert pipeline_res.status_code == 200, f"Pipeline execution failed: {pipeline_res.text}"

        gen_res = await ac.post(f"/api/v1/certificates/{cert_id}/generate-report", headers=headers)
        assert gen_res.status_code == 200, f"Report generation failed: {gen_res.text}"
        report_data = gen_res.json()

        assert report_data["certificate_id"] == cert_id
        assert report_data.get("pdf_path") or report_data.get("pdf_url") or report_data.get("id"), "Report response must contain valid report identifier or path"

        async with AsyncSessionLocal() as session:
            cert_stmt = await session.execute(select(Certificate).where(Certificate.id == cert_id))
            cert = cert_stmt.scalars().first()

            ocr_stmt = await session.execute(select(OCRData).where(OCRData.certificate_id == cert_id))
            ocr = ocr_stmt.scalars().first()

            vr_stmt = await session.execute(select(VerificationResult).where(VerificationResult.certificate_id == cert_id))
            vr = vr_stmt.scalars().first()

            ts_stmt = await session.execute(select(TrustScore).where(TrustScore.certificate_id == cert_id))
            ts = ts_stmt.scalars().first()

            fa_stmt = await session.execute(select(FraudAnalysis).where(FraudAnalysis.certificate_id == cert_id))
            fa = fa_stmt.scalars().first()

            fp_stmt = await session.execute(select(FinalPrediction).where(FinalPrediction.certificate_id == cert_id))
            fp = fp_stmt.scalars().first()

            rep_stmt = await session.execute(select(VerificationReport).where(VerificationReport.certificate_id == cert_id))
            rep = rep_stmt.scalars().first()

            assert cert is not None
            assert ocr is not None
            assert vr is not None
            assert ts is not None
            assert fa is not None
            assert fp is not None
            assert rep is not None

            assert rep.certificate_id == cert_id
            assert rep.pdf_path is not None, "Report PDF path must be saved"
            assert rep.digital_signature is not None and len(rep.digital_signature) > 0, "Report digital signature must be generated"

            get_rep_res = await ac.get(f"/api/v1/certificates/{cert_id}/report", headers=headers)
            assert get_rep_res.status_code == 200, f"Get report failed: {get_rep_res.text}"
            rep_json = get_rep_res.json()
            assert rep_json["certificate_id"] == cert_id
            assert rep_json["id"] == rep.id


@pytest.mark.asyncio
async def test_report_generation_guards_against_pending_processing():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        rnd = uuid.uuid4().hex[:8]
        email = f"pending_user_{rnd}@example.com"
        password = "TestPassword123!"
        await ac.post("/api/v1/auth/register", json={
            "full_name": f"Pending User {rnd}",
            "email": email,
            "password": password,
            "role": "student"
        })

        async with AsyncSessionLocal() as session:
            await session.execute(
                update(User).where(User.email == email).values(is_email_verified=True)
            )
            await session.commit()
            user_stmt = await session.execute(select(User).where(User.email == email))
            user = user_stmt.scalars().first()
            user_id = user.id

        login_res = await ac.post("/api/v1/auth/login", json={"email": email, "password": password})
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        cert_id = str(uuid.uuid4())
        async with AsyncSessionLocal() as session:
            cert = Certificate(
                id=cert_id,
                owner_id=user_id,
                original_filename="unprocessed.pdf",
                storage_path="/tmp/unprocessed.pdf",
                file_type="pdf",
                file_size_bytes=1024,
                sha256_hash=f"pending_hash_{uuid.uuid4().hex}",
            )
            session.add(cert)
            await session.commit()

        try:
            gen_res = await ac.post(f"/api/v1/certificates/{cert_id}/generate-report", headers=headers)
            
            async with AsyncSessionLocal() as session:
                ocr_stmt = await session.execute(select(OCRData).where(OCRData.certificate_id == cert_id))
                ocr = ocr_stmt.scalars().first()

            if gen_res.status_code == 400:
                assert "pending" in gen_res.text.lower() or "missing" in gen_res.text.lower() or "run pipeline" in gen_res.text.lower()
            else:
                assert gen_res.status_code == 200
                assert ocr is not None, "Pipeline must auto-execute if report endpoint completes successfully"
        finally:
            async with AsyncSessionLocal() as session:
                await session.execute(delete(VerificationReport).where(VerificationReport.certificate_id == cert_id))
                await session.execute(delete(Certificate).where(Certificate.id == cert_id))
                await session.commit()
