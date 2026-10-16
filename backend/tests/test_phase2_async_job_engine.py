import uuid
import pytest
import pytest_asyncio
import asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.db.database import AsyncSessionLocal
from app.models.models import (
    User, UserRole, Certificate, Organization, VerificationJob, JobStatus, PipelineStage, AuditLog
)
from app.core.security import hash_password, create_access_token


@pytest_asyncio.fixture
async def async_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_async_job_creation_and_telemetry(async_client):
    async with AsyncSessionLocal() as db:
        rnd = uuid.uuid4().hex[:8]
        org = Organization(name=f"Async Test Org {rnd}", slug=f"async-org-{rnd}", status="active")
        db.add(org)
        await db.flush()

        user = User(
            full_name=f"Async Verifier {rnd}",
            email=f"async_verifier_{rnd}@example.com",
            hashed_password=hash_password("Password123"),
            role=UserRole.UNIVERSITY,
            organization_id=org.id,
            is_active=True,
            is_email_verified=True,
        )
        db.add(user)
        await db.flush()

        cert = Certificate(
            organization_id=org.id,
            owner_id=user.id,
            original_filename="transcript.pdf",
            storage_path="uploads/transcript.pdf",
            file_type="pdf",
            file_size_bytes=2048,
            sha256_hash=f"hash_{uuid.uuid4().hex}",
        )
        db.add(cert)
        await db.commit()

        cert_id = cert.id
        user_id = user.id

    token = create_access_token(subject=user_id, extra_claims={"role": "university"})

    response = await async_client.post(
        f"/api/v1/certificates/{cert_id}/verify-async",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 202, response.text
    job_data = response.json()
    assert "job_id" in job_data
    assert job_data["status"] == "QUEUED"
    job_id = job_data["job_id"]

    await asyncio.sleep(1.0)

    status_resp = await async_client.get(
        f"/api/v1/jobs/{job_id}/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert status_resp.status_code == 200, status_resp.text
    status_data = status_resp.json()
    assert status_data["job_id"] == job_id
    assert status_data["certificate_id"] == cert_id
    assert status_data["status"] in ["PROCESSING", "COMPLETED", "FAILED"]

    async with AsyncSessionLocal() as db:
        rnd_b = uuid.uuid4().hex[:8]
        org_b = Organization(name=f"Other Org {rnd_b}", slug=f"other-org-{rnd_b}", status="active")
        db.add(org_b)
        await db.flush()

        user_b = User(
            full_name=f"User B {rnd_b}",
            email=f"user_b_{rnd_b}@example.com",
            hashed_password=hash_password("Password123"),
            role=UserRole.STUDENT,
            organization_id=org_b.id,
            is_active=True,
            is_email_verified=True,
        )
        db.add(user_b)
        await db.commit()
        user_b_id = user_b.id

    token_b = create_access_token(subject=user_b_id, extra_claims={"role": "student"})

    forbidden_resp = await async_client.get(
        f"/api/v1/jobs/{job_id}/status",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert forbidden_resp.status_code == 403, "Tenant boundary breach! Expected 403 Forbidden"


@pytest.mark.asyncio
async def test_job_retry_handling(async_client):
    async with AsyncSessionLocal() as db:
        rnd = uuid.uuid4().hex[:8]
        org = Organization(name=f"Retry Org {rnd}", slug=f"retry-org-{rnd}", status="active")
        db.add(org)
        await db.flush()

        user = User(
            full_name=f"Retry User {rnd}",
            email=f"retry_user_{rnd}@example.com",
            hashed_password=hash_password("Password123"),
            role=UserRole.ADMIN,
            organization_id=org.id,
            is_active=True,
            is_email_verified=True,
        )
        db.add(user)
        await db.flush()

        cert = Certificate(
            organization_id=org.id,
            owner_id=user.id,
            original_filename="failed_doc.pdf",
            storage_path="uploads/failed_doc.pdf",
            file_type="pdf",
            file_size_bytes=512,
            sha256_hash=f"hash_{uuid.uuid4().hex}",
        )
        db.add(cert)
        await db.flush()

        failed_job = VerificationJob(
            organization_id=org.id,
            certificate_id=cert.id,
            status=JobStatus.FAILED,
            current_stage=PipelineStage.TAMPER_ANALYSIS,
            progress_percentage=65,
            failed_stage="TAMPER_ANALYSIS",
            error_details="Simulated visual processing timeout",
            stage_states={
                "DOCUMENT_ANALYSIS": {"status": "COMPLETED"},
                "OCR": {"status": "COMPLETED"},
                "QR_VERIFICATION": {"status": "COMPLETED"},
                "TAMPER_ANALYSIS": {"status": "FAILED", "error": "Simulated visual processing timeout"},
            },
        )
        db.add(failed_job)
        await db.commit()

        job_id = failed_job.id
        user_id = user.id

    token = create_access_token(subject=user_id, extra_claims={"role": "admin"})

    retry_resp = await async_client.post(
        f"/api/v1/jobs/{job_id}/retry",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert retry_resp.status_code == 202, retry_resp.text
    retry_data = retry_resp.json()
    assert retry_data["job_id"] == job_id
    assert retry_data["status"] == "QUEUED"
