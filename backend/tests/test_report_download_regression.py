"""
Regression test suite for Report Download and Viewing.
Covers:
1. Authenticated download returns 200, application/pdf, valid %PDF- header.
2. Content-Disposition adheres to RFC 5987 (filename*=UTF-8''... and safe ASCII fallback).
3. Inline view mode (inline=true) sets disposition to 'inline'.
4. Safe handling of non-ASCII and Tamil filenames without Latin-1 ASGI crashes.
5. Self-healing auto-regeneration when DB report row exists but disk file was removed.
6. Unauthenticated requests return 401.
7. Tenant/user isolation (User B cannot download User A's report -> 404).
8. Digital signature verification endpoint (/verify-signature) validates integrity.
"""
import os
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import update, select

from app.main import app
from app.db.database import AsyncSessionLocal
from app.models.models import User, Certificate, VerificationReport
from tests.conftest import generate_valid_pdf_bytes


async def create_verified_user(ac: AsyncClient, prefix: str = "user"):
    rnd = uuid.uuid4().hex[:8]
    email = f"{prefix}_{rnd}@example.com"
    password = "TestPassword123!"
    reg_res = await ac.post("/api/v1/auth/register", json={
        "full_name": f"Test {prefix.capitalize()} {rnd}",
        "email": email,
        "password": password,
        "role": "student",
    })
    assert reg_res.status_code == 201, f"User registration failed: {reg_res.text}"

    async with AsyncSessionLocal() as session:
        await session.execute(
            update(User).where(User.email == email).values(is_email_verified=True)
        )
        await session.commit()

    login_res = await ac.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    token = login_res.json()["access_token"]
    return {"email": email, "token": token, "headers": {"Authorization": f"Bearer {token}"}}


async def upload_and_process_certificate(ac: AsyncClient, user: dict, filename: str = "cert.pdf", text: str = "CertiVerify Test Certificate") -> str:
    pdf_bytes = generate_valid_pdf_bytes(text)
    upload_res = await ac.post(
        "/api/v1/certificates/upload",
        files={"files": (filename, pdf_bytes, "application/pdf")},
        headers=user["headers"],
    )
    assert upload_res.status_code == 201, f"Upload failed: {upload_res.text}"
    cert_id = upload_res.json()["certificates"][0]["id"]

    pipe_res = await ac.post(f"/api/v1/certificates/{cert_id}/run-pipeline", headers=user["headers"])
    assert pipe_res.status_code == 200, f"Pipeline run failed: {pipe_res.text}"
    return cert_id


@pytest.mark.asyncio
async def test_report_download_authenticated_and_rfc5987():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        user_a = await create_verified_user(ac, "alice")
        cert_id = await upload_and_process_certificate(ac, user_a, "degree_alice.pdf", "CertiVerify Test Certificate For Alice")

        # Generate report
        gen_res = await ac.post(f"/api/v1/certificates/{cert_id}/generate-report", headers=user_a["headers"])
        assert gen_res.status_code == 200, f"Report generation failed: {gen_res.text}"
        gen_data = gen_res.json()
        verification_id = gen_data["verification_id"]

        # 1. Test Download (attachment)
        down_res = await ac.get(f"/api/v1/certificates/{cert_id}/download-report", headers=user_a["headers"])
        assert down_res.status_code == 200
        assert down_res.headers["content-type"] == "application/pdf"
        assert down_res.content.startswith(b"%PDF-")

        disp = down_res.headers.get("content-disposition", "")
        assert "attachment" in disp
        assert 'filename="' in disp
        assert "filename*=UTF-8''" in disp
        assert verification_id in disp

        # 2. Test Inline view (inline=true)
        inline_res = await ac.get(f"/api/v1/certificates/{cert_id}/download-report?inline=true", headers=user_a["headers"])
        assert inline_res.status_code == 200
        assert inline_res.headers["content-type"] == "application/pdf"
        assert inline_res.content.startswith(b"%PDF-")

        disp_inline = inline_res.headers.get("content-disposition", "")
        assert "inline" in disp_inline
        assert "filename*=UTF-8''" in disp_inline


@pytest.mark.asyncio
async def test_report_download_non_ascii_and_tamil_filename():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        user = await create_verified_user(ac, "tamil_user")

        # Non-ASCII filename containing Tamil characters
        tamil_filename = "சான்றிதழ்_கீர்த்தனா_degree.pdf"
        cert_id = await upload_and_process_certificate(ac, user, tamil_filename, "Tamil Certificate Test: சான்றிதழ்")

        # Generate report
        gen_res = await ac.post(f"/api/v1/certificates/{cert_id}/generate-report", headers=user["headers"])
        assert gen_res.status_code == 200, f"Report generation failed: {gen_res.text}"

        # Download report - must NOT raise UnicodeEncodeError in ASGI headers
        down_res = await ac.get(f"/api/v1/certificates/{cert_id}/download-report", headers=user["headers"])
        assert down_res.status_code == 200
        assert down_res.headers["content-type"] == "application/pdf"
        assert down_res.content.startswith(b"%PDF-")

        disp = down_res.headers.get("content-disposition", "")
        assert "filename*=UTF-8''" in disp
        # The ASCII fallback should have non-ASCII characters replaced safely
        assert 'filename="' in disp


@pytest.mark.asyncio
async def test_report_download_self_healing_when_file_deleted_from_disk():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        user = await create_verified_user(ac, "healer")
        cert_id = await upload_and_process_certificate(ac, user, "heal_test.pdf", "Healing Test Certificate")

        gen_res = await ac.post(f"/api/v1/certificates/{cert_id}/generate-report", headers=user["headers"])
        assert gen_res.status_code == 200

        # Retrieve the generated file path from DB and deliberately delete the file
        async with AsyncSessionLocal() as session:
            stmt = select(VerificationReport).where(VerificationReport.certificate_id == cert_id)
            report_row = (await session.execute(stmt)).scalars().first()
            assert report_row is not None
            disk_path = report_row.pdf_path

        if os.path.exists(disk_path):
            os.remove(disk_path)
        assert not os.path.exists(disk_path), "File should be deleted to test self-healing"

        # Now download - the endpoint must self-heal and regenerate the PDF on disk
        down_res = await ac.get(f"/api/v1/certificates/{cert_id}/download-report", headers=user["headers"])
        assert down_res.status_code == 200
        assert down_res.headers["content-type"] == "application/pdf"
        assert down_res.content.startswith(b"%PDF-")

        # Verify the file was recreated on disk
        async with AsyncSessionLocal() as session:
            stmt = select(VerificationReport).where(VerificationReport.certificate_id == cert_id)
            fresh_row = (await session.execute(stmt)).scalars().first()
            assert fresh_row is not None
            assert os.path.exists(fresh_row.pdf_path)


@pytest.mark.asyncio
async def test_report_download_unauthenticated_returns_401():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        user = await create_verified_user(ac, "auth_user")
        pdf_bytes = generate_valid_pdf_bytes("Auth Test")
        upload_res = await ac.post(
            "/api/v1/certificates/upload",
            files={"files": ("auth_test.pdf", pdf_bytes, "application/pdf")},
            headers=user["headers"],
        )
        cert_id = upload_res.json()["certificates"][0]["id"]

        # Anonymous download without token -> 401
        res = await ac.get(f"/api/v1/certificates/{cert_id}/download-report")
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_report_download_tenant_isolation_returns_404():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        user_a = await create_verified_user(ac, "tenant_a")
        user_b = await create_verified_user(ac, "tenant_b")

        cert_id = await upload_and_process_certificate(ac, user_a, "secret_a.pdf", "Tenant A Certificate")
        await ac.post(f"/api/v1/certificates/{cert_id}/generate-report", headers=user_a["headers"])

        # User B attempts to download User A's certificate report -> 404 Not Found
        res = await ac.get(f"/api/v1/certificates/{cert_id}/download-report", headers=user_b["headers"])
        assert res.status_code == 404


@pytest.mark.asyncio
async def test_report_signature_verification_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        user = await create_verified_user(ac, "signer")
        cert_id = await upload_and_process_certificate(ac, user, "signature_test.pdf", "Signature Test Certificate")
        await ac.post(f"/api/v1/certificates/{cert_id}/generate-report", headers=user["headers"])

        # Check signature verification
        sig_res = await ac.post(f"/api/v1/certificates/{cert_id}/verify-signature", headers=user["headers"])
        assert sig_res.status_code == 200
        sig_data = sig_res.json()
        assert sig_data["is_valid"] is True
        assert sig_data["verification_id"].startswith("CV-")
        assert "valid" in sig_data["detail"].lower()
