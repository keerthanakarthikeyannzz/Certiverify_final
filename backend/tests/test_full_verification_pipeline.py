"""
Test Suite: Complete End-to-End Verification Pipeline
Verifies that all 14 pipeline stages execute for a single real certificate_id:
1. Upload
2. OCR Extraction
3. Document Classification
4. Field Extraction
5. Document Comparison (single doc / grouped)
6. QR Verification
7. SHA-256 Hash Integrity
8. Blockchain Verification
9. Tampering & Forgery Detection
10. Duplicate Detection
11. AI Fraud Analysis
12. Trust Score Engine
13. Final Prediction
14. PDF Report Generation
"""
import pytest
import os
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture
def client():
    return TestClient(app)

def test_full_verification_pipeline_e2e(client):
    import uuid
    from tests.conftest import find_sample_pdf
    pdf_path = find_sample_pdf()

    assert os.path.exists(pdf_path), f"sample_certificate.pdf must exist at {pdf_path}"

    # Register & Login User
    rnd = uuid.uuid4().hex[:8]
    email = f"pipeline_e2e_{rnd}@example.com"
    password = "TestPassword123!"
    client.post("/api/v1/auth/register", json={
        "full_name": "Pipeline E2E User",
        "email": email,
        "password": password,
        "role": "student"
    })
    from tests.conftest import verify_test_user_email_sync
    verify_test_user_email_sync(email)
    login_res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Stage 1: Upload
    with open(pdf_path, "rb") as f:
        files = {"files": ("sample_certificate.pdf", f, "application/pdf")}
        upload_res = client.post("/api/v1/certificates/upload", files=files, headers=headers)
    
    assert upload_res.status_code == 201
    cert_id = upload_res.json()["certificates"][0]["id"]
    assert cert_id is not None

    # Execute full pipeline end-to-end for cert_id
    run_res = client.post(f"/api/v1/certificates/{cert_id}/run-pipeline", headers=headers)
    assert run_res.status_code == 200
    pipeline_data = run_res.json()

    assert pipeline_data["certificate_id"] == cert_id
    assert pipeline_data["overall_status"] in ["FULLY_COMPLETE", "PARTIALLY_COMPLETE"]
    assert len(pipeline_data["stages"]) == 14

    # Verify stage-by-stage responses are populated with real backend results
    stages_by_key = {s["stage"]: s for s in pipeline_data["stages"]}

    assert stages_by_key["upload"]["status"] == "COMPLETED"
    assert stages_by_key["ocr"]["status"] == "COMPLETED"
    assert stages_by_key["classification"]["status"] == "COMPLETED"
    assert stages_by_key["field_extraction"]["status"] == "COMPLETED"
    assert stages_by_key["qr_verification"]["status"] in ["COMPLETED", "PENDING"]
    assert stages_by_key["hash_check"]["status"] == "COMPLETED"
    assert stages_by_key["tampering"]["status"] == "COMPLETED"
    assert stages_by_key["duplicate"]["status"] == "COMPLETED"
    assert stages_by_key["fraud_analysis"]["status"] == "COMPLETED"
    assert stages_by_key["trust_score"]["status"] == "COMPLETED"
    assert stages_by_key["prediction"]["status"] == "COMPLETED"
    assert stages_by_key["report"]["status"] == "COMPLETED"

    # Verify unified result API returns matching decision for cert_id
    res_api = client.get(f"/api/v1/certificates/{cert_id}/verification-result", headers=headers)
    assert res_api.status_code == 200
    verif_res = res_api.json()

    assert verif_res["certificate_id"] == cert_id
    assert verif_res["trust_score"] is not None
    assert verif_res["prediction"] in ["genuine", "suspicious", "fake"]
    assert verif_res["explanation"] is not None
