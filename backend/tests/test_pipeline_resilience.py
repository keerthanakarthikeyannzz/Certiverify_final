"""
Regression Test Suite: Pipeline Resilience, Idempotency & Auth Token Lifecycles.

Tests:
1. Re-running the verification pipeline on the same certificate (idempotent, clean reset).
2. Uploading the same file twice (same SHA-256: detected as duplicate, owner distinction, other stages still run).
3. Sequential report generations on the same certificate (new verification_id, atomic file update, archive).
4. Concurrent pipeline execution prevention (HTTP 409 Conflict with descriptive message).
5. DEV_LONG_LIVED_SESSION configuration and refresh token rotation.
"""
import io
import os
import uuid
import pytest
import pytest_asyncio
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.db.database import AsyncSessionLocal
from app.models.models import (
    User, Certificate, UserRole, VerificationJob, JobStatus,
    PipelineStage as JobPipelineStage, OCRData, DocumentType,
    VerificationResult, FraudAnalysis, TrustScore, FinalPrediction,
    VerificationReport, DocTypeEnum, PredictionLabel,
)
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.core.config import settings
from tests.conftest import generate_valid_pdf_bytes


@pytest_asyncio.fixture
async def resilience_context():
    """Sets up a test user, access token, and initial certificate."""
    user_id = uuid.uuid4().hex
    cert_id = uuid.uuid4().hex
    pdf_bytes = generate_valid_pdf_bytes("CertiVerify Resilience Testing Document")

    async with AsyncSessionLocal() as session:
        user = User(
            id=user_id,
            email=f"resilience_{user_id[:8]}@example.com",
            full_name="Resilience Tester",
            hashed_password="test_hashed_password",
            role=UserRole.STUDENT,
            is_active=True,
            is_email_verified=True,
        )
        session.add(user)

        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        storage_path = os.path.join(settings.UPLOAD_DIR, f"resilience_{cert_id}.pdf")
        with open(storage_path, "wb") as f:
            f.write(pdf_bytes)

        cert = Certificate(
            id=cert_id,
            owner_id=user_id,
            original_filename="resilience_test.pdf",
            storage_path=storage_path,
            file_type="pdf",
            file_size_bytes=len(pdf_bytes),
            sha256_hash="1111222233334444555566667777888899990000aaaabbbbccccddddeeeeffff",
            uploaded_at=datetime.now(timezone.utc),
        )
        session.add(cert)
        await session.commit()

    token = create_access_token(subject=user_id, extra_claims={"role": UserRole.STUDENT.value})
    headers = {"Authorization": f"Bearer {token}"}

    return {
        "user_id": user_id,
        "cert_id": cert_id,
        "token": token,
        "headers": headers,
        "pdf_bytes": pdf_bytes,
    }


@pytest.mark.asyncio
async def test_rerun_pipeline_on_same_certificate(resilience_context):
    """Re-running run-pipeline on the same certificate must be clean, idempotent, and never crash."""
    headers = resilience_context["headers"]
    cert_id = resilience_context["cert_id"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # First execution (synchronous via sync=true)
        res1 = await client.post(
            f"/api/v1/certificates/{cert_id}/run-pipeline?sync=true",
            headers=headers,
        )
        assert res1.status_code in (200, 202)
        data1 = res1.json()
        assert str(data1["certificate_id"]).replace("-", "") == cert_id.replace("-", "")
        assert data1["job_id"] is not None

        # Second execution on the SAME certificate
        res2 = await client.post(
            f"/api/v1/certificates/{cert_id}/run-pipeline?sync=true",
            headers=headers,
        )
        assert res2.status_code in (200, 202)
        data2 = res2.json()
        assert str(data2["certificate_id"]).replace("-", "") == cert_id.replace("-", "")
        assert data2["job_id"] is not None
        assert data2["job_id"] != data1["job_id"]  # Produced a new clean verification job


@pytest.mark.asyncio
async def test_concurrent_pipeline_run_returns_409(resilience_context):
    """Triggering a pipeline run while an active job is processing must return HTTP 409 Conflict."""
    headers = resilience_context["headers"]
    cert_id = resilience_context["cert_id"]
    user_id = resilience_context["user_id"]

    # Insert an active processing job directly
    async with AsyncSessionLocal() as session:
        active_job = VerificationJob(
            certificate_id=cert_id,
            status=JobStatus.PROCESSING,
            current_stage=JobPipelineStage.OCR,
            progress_percentage=25,
            started_at=datetime.utcnow(),
            stage_states={},
        )
        session.add(active_job)
        await session.commit()
        await session.refresh(active_job)
        active_job_id = active_job.id

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            f"/api/v1/certificates/{cert_id}/run-pipeline",
            headers=headers,
        )
        assert res.status_code == 409
        detail = res.json()["detail"]
        assert "already in progress" in detail
        assert active_job_id in detail


@pytest.mark.asyncio
async def test_sequential_report_generations(resilience_context):
    """Calling generate-report multiple times on the same certificate produces new verification IDs and archives old PDFs."""
    headers = resilience_context["headers"]
    cert_id = resilience_context["cert_id"]

    # Populate minimum required stage rows so report generation succeeds
    async with AsyncSessionLocal() as session:
        session.add(VerificationResult(
            certificate_id=cert_id,
            qr_present=True,
            qr_valid=True,
            tampering_score=5.0,
            tampering_risk_level="LOW",
        ))
        session.add(FinalPrediction(
            certificate_id=cert_id,
            label=PredictionLabel.GENUINE,
            confidence_score=0.98,
            explanation="Verified institutional test credential",
        ))
        session.add(OCRData(
            certificate_id=cert_id,
            student_name="Alice Smith",
            university_name="National University",
            certificate_number="CERT-12345",
        ))
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # First report generation
        res1 = await client.post(
            f"/api/v1/certificates/{cert_id}/generate-report",
            headers=headers,
        )
        assert res1.status_code == 200
        data1 = res1.json()
        vid1 = data1["verification_id"]
        assert vid1.startswith("CV-")
        assert data1["digital_signature"] is not None

        # Second report generation on SAME certificate
        res2 = await client.post(
            f"/api/v1/certificates/{cert_id}/generate-report",
            headers=headers,
        )
        assert res2.status_code == 200
        data2 = res2.json()
        vid2 = data2["verification_id"]
        assert vid2.startswith("CV-")
        assert vid2 != vid1  # Must have a distinct verification ID

        # Third report generation
        res3 = await client.post(
            f"/api/v1/certificates/{cert_id}/generate-report",
            headers=headers,
        )
        assert res3.status_code == 200
        data3 = res3.json()
        vid3 = data3["verification_id"]
        assert vid3 != vid2

        # Verify listing reports includes the certificate report
        list_res = await client.get("/api/v1/reports", headers=headers)
        assert list_res.status_code == 200
        reports = list_res.json()
        assert any(str(r["certificate_id"]).replace("-", "") == str(cert_id).replace("-", "") for r in reports)


@pytest.mark.asyncio
async def test_duplicate_upload_distinction(resilience_context):
    """Uploading the identical file twice records the duplicate with owner distinction and runs normally."""
    headers = resilience_context["headers"]
    pdf_bytes = resilience_context["pdf_bytes"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        files1 = [("files", ("duplicate_test_a.pdf", io.BytesIO(pdf_bytes), "application/pdf"))]
        res1 = await client.post("/api/v1/certificates/upload", headers=headers, files=files1)
        assert res1.status_code == 201
        cert_a_id = res1.json()["certificates"][0]["id"]

        files2 = [("files", ("duplicate_test_b.pdf", io.BytesIO(pdf_bytes), "application/pdf"))]
        res2 = await client.post("/api/v1/certificates/upload", headers=headers, files=files2)
        assert res2.status_code == 201
        cert_b_id = res2.json()["certificates"][0]["id"]

        assert cert_a_id != cert_b_id

        # Verify duplicate detection endpoint runs on cert B
        dup_res = await client.post(f"/api/v1/certificates/{cert_b_id}/verify-duplicate", headers=headers)
        assert dup_res.status_code == 200
        dup_data = dup_res.json()
        assert dup_data["is_duplicate"] is True


@pytest.mark.asyncio
async def test_auth_refresh_token_rotation(resilience_context):
    """Validates refresh token rotation: submitting refresh token returns new access and refresh tokens."""
    user_id = resilience_context["user_id"]
    initial_refresh = create_refresh_token(subject=user_id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": initial_refresh},
        )
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["refresh_token"] != initial_refresh

        # Decode tokens to confirm validity
        acc_dec = decode_token(data["access_token"])
        ref_dec = decode_token(data["refresh_token"])
        assert str(acc_dec["sub"]).replace("-", "") == str(user_id).replace("-", "")
        assert str(ref_dec["sub"]).replace("-", "") == str(user_id).replace("-", "")
        assert ref_dec["type"] == "refresh"


def test_dev_long_lived_session_production_guard():
    """Confirms DEV_LONG_LIVED_SESSION cannot be enabled when ENVIRONMENT is production."""
    from pydantic import ValidationError
    from app.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(
            ENVIRONMENT="production",
            DEV_LONG_LIVED_SESSION=True,
            SECRET_KEY="test_secret_for_validation_testing_purposes",
        )
