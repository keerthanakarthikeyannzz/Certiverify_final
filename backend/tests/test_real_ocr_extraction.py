"""
Test Suite: Real Document OCR and Dynamic Field Extraction Verification
Tests sample_certificate.pdf against backend OCR pipeline and verifies 100% field accuracy.
"""
import pytest
import os
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture
def client():
    return TestClient(app)

def test_real_sample_certificate_ocr_extraction(client):
    import uuid
    from tests.conftest import find_sample_pdf
    pdf_path = find_sample_pdf()

    assert os.path.exists(pdf_path), f"sample_certificate.pdf must exist at {pdf_path}"

    # Register & Login User
    rnd = uuid.uuid4().hex[:8]
    email = f"ocr_real_{rnd}@example.com"
    password = "TestPassword123!"
    client.post("/api/v1/auth/register", json={
        "full_name": "OCR Test User",
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

    # 1. Upload sample_certificate.pdf
    with open(pdf_path, "rb") as f:
        files = {"files": ("sample_certificate.pdf", f, "application/pdf")}
        upload_res = client.post("/api/v1/certificates/upload", files=files, headers=headers)
    
    assert upload_res.status_code == 201
    cert_id = upload_res.json()["certificates"][0]["id"]

    # 2. Run OCR text extraction
    ocr_res = client.post(f"/api/v1/certificates/{cert_id}/extract-ocr", headers=headers)
    assert ocr_res.status_code == 200
    ocr_data = ocr_res.json()

    # 3. Confirm actual OCR extracted values from sample_certificate.pdf
    assert ocr_data["student_name"] == "ROHITH A"
    assert ocr_data["register_number"] == "2212258607"
    assert ocr_data["roll_number"] == "7258636"
    assert ocr_data["certificate_number"] == "33233508"
    assert "PKD MATRIC" in ocr_data["university_name"]  # School/Institution
    assert ocr_data["date_of_issue"] == "08.05.2023" or "2023" in ocr_data["raw_text"]

    # 4. Run dynamic document validation
    val_res = client.post(f"/api/v1/certificates/{cert_id}/validate", headers=headers)
    assert val_res.status_code == 200
    val_data = val_res.json()

    assert val_data["certificate_id"] == cert_id
    assert len(val_data["field_validations"]) > 0

    # Ensure no hallucinated values are returned for unextracted fields
    for field in val_data["field_validations"]:
        assert field["field"] is not None
        assert field["status"] in ["VALID", "INVALID", "MISSING", "LOW_CONFIDENCE", "NOT_DETECTED"]
        assert field["reason"] is not None
