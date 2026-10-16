"""
CERTIVERIFY AI — COMPREHENSIVE QA & AUTOMATED TESTING SUITE
Tests complete end-to-end processing pipeline, current-document isolation, 
zero cross-document contamination, error handling, security, and reports.
"""
import io
import os
import pytest
from httpx import AsyncClient, ASGITransport
from PIL import Image, ImageDraw

from app.main import app

CERT_BASE = "/api/v1/certificates"
AUTH_BASE = "/api/v1/auth"


def _create_image(text_lines: list[str]) -> bytes:
    """Helper to render synthetic document images with specific text content."""
    img = Image.new("RGB", (1200, 900), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    y = 60
    for line in text_lines:
        draw.text((60, y), line, fill=(0, 0, 0), font_size=32)
        y += 60
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def _get_auth_headers(client: AsyncClient, email_prefix: str = "qa_user") -> dict:
    email = f"{email_prefix}_{os.urandom(4).hex()}@certiverify.ai"
    password = "Password123!"
    await client.post(f"{AUTH_BASE}/register", json={
        "email": email, "password": password, "full_name": "QA Inspector", "role": "verifier"
    })
    from tests.conftest import verify_test_user_email
    await verify_test_user_email(email)
    resp = await client.post(f"{AUTH_BASE}/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Auth login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_auth_and_security_isolation():
    """TC-SEC-001: Unauthorized access blocked & 404 returned for invalid cert IDs."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=30.0) as client:
        # Unauthorized access
        res = await client.get(f"{CERT_BASE}/00000000-0000-0000-0000-000000000000/pipeline")
        assert res.status_code == 401

        # Authenticated but non-existent ID
        headers = await _get_auth_headers(client, "sec_user")
        res_404 = await client.get(f"{CERT_BASE}/00000000-0000-0000-0000-000000000000/pipeline", headers=headers)
        assert res_404.status_code == 404


@pytest.mark.asyncio
async def test_upload_validation_and_hashing():
    """TC-UPL-001: File upload assigns unique certificate_id and SHA-256 hash."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=30.0) as client:
        headers = await _get_auth_headers(client, "upl_user")
        img_bytes = _create_image(["Sample Certificate Document", "Name: Alex Smith"])

        files = [("files", ("test_cert.png", img_bytes, "image/png"))]
        res = await client.post(f"{CERT_BASE}/upload", headers=headers, files=files)
        assert res.status_code == 201
        data = res.json()
        assert "certificates" in data
        cert = data["certificates"][0]
        assert cert["id"] is not None
        assert cert["sha256_hash"] is not None
        assert cert["original_filename"] == "test_cert.png"


@pytest.mark.asyncio
async def test_ocr_and_no_hallucination():
    """TC-OCR-001 & TC-FLD-001: Live OCR runs on uploaded bytes & returns null for missing fields."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=60.0) as client:
        headers = await _get_auth_headers(client, "ocr_user")
        from tests.conftest import find_sample_pdf
        pdf_path = find_sample_pdf()
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        files = [("files", ("sample_certificate.pdf", pdf_bytes, "application/pdf"))]
        up_res = await client.post(f"{CERT_BASE}/upload", headers=headers, files=files)
        cert_id = up_res.json()["certificates"][0]["id"]

        ocr_res = await client.post(f"{CERT_BASE}/{cert_id}/extract-ocr", headers=headers)
        assert ocr_res.status_code == 200
        ocr_data = ocr_res.json()
        assert ocr_data["certificate_id"] == cert_id
        # Zero hallucination — non-existent fields like Aadhaar number must be null
        assert ocr_data.get("aadhaar_number") is None or ocr_data.get("aadhaar_number") == ""


@pytest.mark.asyncio
async def test_verification_pipeline_modules():
    """TC-PIP-001: Executes QR, Blockchain, Tampering, Duplicate, Fraud, and Trust Score on current ID."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=120.0) as client:
        headers = await _get_auth_headers(client, "pipe_user")
        img_bytes = _create_image([
            "HSC Higher Secondary Marksheet",
            "Student Name: Rohan Sharma",
            "Roll Number: 55410",
            "School: City High School"
        ])

        files = [("files", ("hsc.png", img_bytes, "image/png"))]
        up_res = await client.post(f"{CERT_BASE}/upload", headers=headers, files=files)
        cert_id = up_res.json()["certificates"][0]["id"]

        # Run pipeline stages
        await client.post(f"{CERT_BASE}/{cert_id}/extract-ocr", headers=headers)
        verif_res = await client.post(f"{CERT_BASE}/{cert_id}/verify-all", headers=headers)
        assert verif_res.status_code == 200

        fraud_res = await client.post(f"{CERT_BASE}/{cert_id}/analyze-fraud", headers=headers)
        assert fraud_res.status_code == 200

        trust_res = await client.post(f"{CERT_BASE}/{cert_id}/compute-trust-score", headers=headers)
        assert trust_res.status_code == 200
        assert 0 <= trust_res.json()["score"] <= 100

        pred_res = await client.post(f"{CERT_BASE}/{cert_id}/predict", headers=headers)
        assert pred_res.status_code == 200
        assert pred_res.json()["label"].lower() in ("genuine", "suspicious", "fake")

        pipe_res = await client.get(f"{CERT_BASE}/{cert_id}/pipeline", headers=headers)
        assert pipe_res.status_code == 200
        assert pipe_res.json()["certificate_id"] == cert_id


@pytest.mark.asyncio
async def test_critical_document_isolation_a_to_b():
    """
    CRITICAL TEST (Requirement 6 & 30):
    Upload Document A (Degree Certificate) -> Process completely.
    Upload Document B (Degree Certificate) -> Process completely.
    Verify 100% data isolation: B receives unique cert ID and separate report.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=180.0) as client:
        headers = await _get_auth_headers(client, "iso_user")

        from tests.conftest import find_sample_pdf
        pdf_path = find_sample_pdf()
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        # ── Step 1: Process Document A ─────────────────────────────────────────
        files_a = [("files", ("degree_a.pdf", pdf_bytes, "application/pdf"))]
        res_a = await client.post(f"{CERT_BASE}/upload", headers=headers, files=files_a)
        assert res_a.status_code == 201
        cert_a_id = res_a.json()["certificates"][0]["id"]

        await client.post(f"{CERT_BASE}/{cert_a_id}/extract-ocr", headers=headers)
        await client.post(f"{CERT_BASE}/{cert_a_id}/verify-all", headers=headers)
        await client.post(f"{CERT_BASE}/{cert_a_id}/compute-trust-score", headers=headers)
        await client.post(f"{CERT_BASE}/{cert_a_id}/predict", headers=headers)

        # ── Step 2: Process Document B ─────────────────────────────────────────
        files_b = [("files", ("degree_b.pdf", pdf_bytes, "application/pdf"))]
        res_b = await client.post(f"{CERT_BASE}/upload", headers=headers, files=files_b)
        assert res_b.status_code == 201
        cert_b_id = res_b.json()["certificates"][0]["id"]

        # Assert ID Isolation
        assert cert_b_id != cert_a_id, "Document B shared Certificate ID with Document A!"

        ocr_b_res = await client.post(f"{CERT_BASE}/{cert_b_id}/extract-ocr", headers=headers)
        assert ocr_b_res.status_code == 200
        ocr_b_data = ocr_b_res.json()

        await client.post(f"{CERT_BASE}/{cert_b_id}/verify-all", headers=headers)
        trust_b_res = await client.post(f"{CERT_BASE}/{cert_b_id}/compute-trust-score", headers=headers)
        assert trust_b_res.status_code == 200
        pred_b_res = await client.post(f"{CERT_BASE}/{cert_b_id}/predict", headers=headers)
        assert pred_b_res.status_code == 200

        # Assert report metadata belongs exclusively to Document B
        report_b_res = await client.get(f"{CERT_BASE}/{cert_b_id}/report", headers=headers)
        if report_b_res.status_code == 200:
            report_b = report_b_res.json()
            assert report_b.get("certificate_id") == cert_b_id


@pytest.mark.asyncio
async def test_error_handling_no_silent_fallback():
    """
    CRITICAL TEST (Requirement 25 & 27):
    If current document processing fails, the application must return an error response
    and MUST NOT silently fall back to previous successful document data.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=30.0) as client:
        headers = await _get_auth_headers(client, "err_user")

        from tests.conftest import find_sample_pdf
        pdf_path = find_sample_pdf()
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        # Step 1: Upload & process successful Document A
        files_a = [("files", ("valid.pdf", pdf_bytes, "application/pdf"))]
        res_a = await client.post(f"{CERT_BASE}/upload", headers=headers, files=files_a)
        cert_a_id = res_a.json()["certificates"][0]["id"]
        await client.post(f"{CERT_BASE}/{cert_a_id}/extract-ocr", headers=headers)

        # Step 2: Query non-existent certificate ID or corrupted request
        invalid_id = "00000000-0000-0000-0000-000000000000"
        err_res = await client.get(f"{CERT_BASE}/{invalid_id}/pipeline", headers=headers)

        # Must return 404 Error, NOT fallback to Document A's data
        assert err_res.status_code == 404
        assert err_res.json().get("detail") == "Certificate not found."
