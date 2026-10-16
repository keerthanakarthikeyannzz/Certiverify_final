"""
Test Context Isolation & Multi-Upload Session Safety (Requirement 28)
Ensures that processing Document B immediately after Document A results in 
100% isolated processing with ZERO data leakage / contamination from Document A.
"""
import io
import pytest
from httpx import AsyncClient, ASGITransport
from PIL import Image, ImageDraw

from app.main import app

CERT_BASE = "/api/v1/certificates"
AUTH_BASE = "/api/v1/auth"


def _create_test_image_bytes(text_lines: list[str]) -> bytes:
    """Helper to create a fresh PNG image in memory with specified text lines."""
    img = Image.new("RGB", (800, 600), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    y = 50
    for line in text_lines:
        draw.text((50, y), line, fill=(0, 0, 0))
        y += 40
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def _get_auth_headers(client: AsyncClient) -> dict:
    import uuid
    email = f"iso_user_{uuid.uuid4().hex[:8]}@example.com"
    password = "Password123!"
    await client.post(f"{AUTH_BASE}/register", json={
        "email": email, "password": password, "full_name": "Iso Tester", "role": "verifier"
    })
    from tests.conftest import verify_test_user_email
    await verify_test_user_email(email)
    resp = await client.post(f"{AUTH_BASE}/login", json={"email": email, "password": password})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_session_upload_context_isolation():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=120.0) as client:
        headers = await _get_auth_headers(client)

        # ── 1. Upload Document A (Student: Rahul Kumar, Degree Certificate) ────
        doc_a_bytes = _create_test_image_bytes([
            "Degree Certificate of Higher Education",
            "Student Name: Rahul Kumar",
            "Register Number: REG-100200",
            "University: National Institute of Science",
            "Degree: Bachelor of Science",
            "Year of Issue: 2023"
        ])

        files_a = [("files", ("document_a.png", doc_a_bytes, "image/png"))]
        resp_a = await client.post(f"{CERT_BASE}/upload", headers=headers, files=files_a)
        assert resp_a.status_code == 201
        cert_a_id = resp_a.json()["certificates"][0]["id"]
        cert_a_hash = resp_a.json()["certificates"][0]["sha256_hash"]

        # Run OCR on Document A
        ocr_res_a = await client.post(f"{CERT_BASE}/{cert_a_id}/extract-ocr", headers=headers)
        assert ocr_res_a.status_code == 200
        data_a = ocr_res_a.json()
        assert data_a["certificate_id"] == cert_a_id

        # ── 2. Upload Document B (Student: Priya Sharma, Aadhaar Card) ─────────
        doc_b_bytes = _create_test_image_bytes([
            "Government of India",
            "Aadhaar Card",
            "Name: Priya Sharma",
            "DOB: 15/08/1998",
            "Gender: Female",
            "Aadhaar Number: 9988 7766 5544"
        ])

        files_b = [("files", ("document_b.png", doc_b_bytes, "image/png"))]
        resp_b = await client.post(f"{CERT_BASE}/upload", headers=headers, files=files_b)
        assert resp_b.status_code == 201
        cert_b_id = resp_b.json()["certificates"][0]["id"]
        cert_b_hash = resp_b.json()["certificates"][0]["sha256_hash"]

        # Verify Document B receives its own unique Certificate ID and Hash
        assert cert_b_id != cert_a_id
        assert cert_b_hash != cert_a_hash

        # Run OCR on Document B
        ocr_res_b = await client.post(f"{CERT_BASE}/{cert_b_id}/extract-ocr", headers=headers)
        assert ocr_res_b.status_code == 200
        data_b = ocr_res_b.json()
        assert data_b["certificate_id"] == cert_b_id

        # Verify ZERO data contamination from Document A to Document B
        raw_text_b = (data_b.get("raw_text") or "").lower()
        assert "rahul kumar" not in raw_text_b, "Document A candidate name leaked into Document B OCR!"
        assert "reg-100200" not in raw_text_b, "Document A register number leaked into Document B OCR!"
