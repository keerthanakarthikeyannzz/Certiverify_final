"""
Test Suite: QR Code Verification
Tests real QR detection, decoding, and validation across documents:
1. Document WITHOUT QR code -> returns NOT DETECTED (present=False, decoded=None)
2. Document WITH valid QR code -> detects, decodes payload, validates
3. Document with invalid/corrupted QR payload -> returns DECODE FAILED / invalid warning
"""
import pytest
import os
import io
import json
from PIL import Image
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture
def client():
    return TestClient(app)

def create_document_with_qr(qr_payload_str: str) -> bytes:
    """Helper to generate a PNG image document with an embedded QR code."""
    import qrcode
    qr = qrcode.QRCode(version=1, box_size=6, border=4)
    qr.add_data(qr_payload_str)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    qw, qh = qr_img.size

    # Composite QR code onto a document canvas within valid bounds
    doc_img = Image.new("RGB", (800, 1000), color="white")
    doc_img.paste(qr_img, (800 - qw - 40, 1000 - qh - 40))

    buf = io.BytesIO()
    doc_img.save(buf, format="PNG")
    return buf.getvalue()

def create_document_without_qr() -> bytes:
    """Helper to generate a clean PNG document image without any QR code."""
    doc_img = Image.new("RGB", (800, 1000), color="white")
    buf = io.BytesIO()
    doc_img.save(buf, format="PNG")
    return buf.getvalue()


def test_qr_verification_flow(client):
    # Register & Login User
    email = "qr_test_user@example.com"
    password = "TestPassword123!"
    client.post("/api/v1/auth/register", json={
        "full_name": "QR Test User",
        "email": email,
        "password": password,
        "role": "student"
    })
    from tests.conftest import verify_test_user_email_sync
    verify_test_user_email_sync(email)
    login_res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # ── 1. Test Document WITHOUT QR Code ─────────────────────────────────────
    no_qr_bytes = create_document_without_qr()
    files_no_qr = {"files": ("no_qr_doc.png", io.BytesIO(no_qr_bytes), "image/png")}
    upload1 = client.post("/api/v1/certificates/upload", files=files_no_qr, headers=headers)
    assert upload1.status_code == 201
    cert1_id = upload1.json()["certificates"][0]["id"]

    qr1_res = client.post(f"/api/v1/certificates/{cert1_id}/verify-qr", headers=headers)
    assert qr1_res.status_code == 200
    qr1_data = qr1_res.json()

    assert qr1_data["qr_present"] is False
    assert qr1_data["qr_decoded_data"] is None
    assert qr1_data["qr_warning"] is not None
    assert "No QR code detected" in qr1_data["qr_warning"]

    # ── 2. Test Document WITH Valid Structured QR Payload ─────────────────────
    valid_payload = json.dumps({
        "certificate_id": cert1_id,
        "verification_token": "VERIF-TOKEN-998877",
        "university_url": "https://verify.university.edu"
    })
    with_qr_bytes = create_document_with_qr(valid_payload)
    files_qr = {"files": ("with_qr_doc.png", io.BytesIO(with_qr_bytes), "image/png")}
    upload2 = client.post("/api/v1/certificates/upload", files=files_qr, headers=headers)
    assert upload2.status_code == 201
    cert2_id = upload2.json()["certificates"][0]["id"]

    qr2_res = client.post(f"/api/v1/certificates/{cert2_id}/verify-qr", headers=headers)
    assert qr2_res.status_code == 200
    qr2_data = qr2_res.json()

    assert qr2_data["qr_present"] is True
    assert qr2_data["qr_decoded_data"] is not None
    assert qr2_data["qr_decoded_data"]["verification_token"] == "VERIF-TOKEN-998877"
    assert qr2_data["qr_valid"] is True

    # ── 3. Test Document WITH Invalid QR Payload ─────────────────────────────
    invalid_payload = "CORRUPTED_RAW_TEXT_INVALID_PAYLOAD"
    bad_qr_bytes = create_document_with_qr(invalid_payload)
    files_bad_qr = {"files": ("bad_qr_doc.png", io.BytesIO(bad_qr_bytes), "image/png")}
    upload3 = client.post("/api/v1/certificates/upload", files=files_bad_qr, headers=headers)
    assert upload3.status_code == 201
    cert3_id = upload3.json()["certificates"][0]["id"]

    qr3_res = client.post(f"/api/v1/certificates/{cert3_id}/verify-qr", headers=headers)
    assert qr3_res.status_code == 200
    qr3_data = qr3_res.json()

    assert qr3_data["qr_present"] is True
    assert qr3_data["qr_valid"] is False
    assert qr3_data["qr_warning"] is not None
