"""
Test Suite: Tampering & AI Forensic Investigation
Validates real forensic evidence signals and tampering results for current certificate:
- ELA compression analysis
- Image quality & noise
- Metadata anomalies
- Copy-paste / clone detection
- Font & typography consistency
- Text alignment & document structure
- Verification details binding to certificate_id
"""
import pytest
import io
import json
from PIL import Image
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture
def client():
    return TestClient(app)

def create_sample_doc(color="white") -> bytes:
    doc_img = Image.new("RGB", (800, 1000), color=color)
    buf = io.BytesIO()
    doc_img.save(buf, format="PNG")
    return buf.getvalue()

def test_tampering_investigation_flow(client):
    # 1. Register & Login
    email = "investigation_user@example.com"
    password = "TestPassword123!"
    client.post("/api/v1/auth/register", json={
        "full_name": "Investigation User",
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

    # 2. Upload Document
    doc_bytes = create_sample_doc("white")
    files = {"files": ("forensic_test.png", io.BytesIO(doc_bytes), "image/png")}
    upload_res = client.post("/api/v1/certificates/upload", files=files, headers=headers)
    assert upload_res.status_code == 201
    cert_id = upload_res.json()["certificates"][0]["id"]

    # 3. Execute Tampering & Forensic Investigation
    tamp_res = client.post(f"/api/v1/certificates/{cert_id}/verify-tampering", headers=headers)
    assert tamp_res.status_code == 200
    data = tamp_res.json()

    assert data["certificate_id"] == cert_id
    assert data["tampering_score"] is not None
    assert data["tampering_risk_level"] is not None
    assert data["tampering_confidence"] is not None
    assert isinstance(data["tampering_flags"], list)
    
    # 4. Verify Forensic Detail Signals
    detail = data["tampering_detail"]
    assert detail is not None
    assert "ela" in detail
    assert "image_quality" in detail
    assert "metadata" in detail
    assert "copy_paste" in detail
    assert "font_consistency" in detail
    assert "text_analysis" in detail
    assert "findings" in detail

    # 5. Fetch Complete Verification Details
    verif_res = client.get(f"/api/v1/certificates/{cert_id}/verification", headers=headers)
    assert verif_res.status_code == 200
    v_data = verif_res.json()
    assert v_data["tampering_score"] == data["tampering_score"]
    assert v_data["tampering_risk_level"] == data["tampering_risk_level"]
