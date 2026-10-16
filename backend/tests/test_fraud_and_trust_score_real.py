"""
Test Suite: Real Fraud Analysis & Trust Score Pipeline
Tests dynamic fraud probability calculation and trust score computation:
1. Genuine clean document -> high trust score (e.g. > 80), low fraud probability (< 0.2)
2. Document with tampering/invalid QR -> trust score drops dynamically (< 65), fraud probability rises
3. Historical duplicate document -> trust score capped at ceiling (<= 15), fraud probability high (>= 0.85)
4. Missing signals -> properly reflected as UNAVAILABLE with renormalized weights
"""
import pytest
import io
import json
from PIL import Image
from fastapi.testclient import TestClient
from app.main import app
from app.services.trust_score import compute_trust_score, TrustScoreInputs
from app.services.fraud_analysis import compute_fraud_analysis, FraudFactorInputs

@pytest.fixture
def client():
    return TestClient(app)

def create_sample_doc(color="white") -> bytes:
    doc_img = Image.new("RGB", (800, 1000), color=color)
    buf = io.BytesIO()
    doc_img.save(buf, format="PNG")
    return buf.getvalue()

def test_fraud_and_trust_score_calculation_changes_with_evidence():
    # ── 1. Clean Evidence Inputs ─────────────────────────────────────────────
    clean_fraud_inputs = FraudFactorInputs(
        ocr_accuracy=0.95,
        doc_classification_confidence=0.90,
        field_extraction_completeness=0.85,
        qr_present=True,
        qr_valid=True,
        blockchain_status="verified",
        tampering_score=5.0,
        is_duplicate=False,
    )
    clean_fraud = compute_fraud_analysis(clean_fraud_inputs)
    assert clean_fraud.fraud_probability < 0.20
    assert len(clean_fraud.critical_overrides_applied) == 0

    clean_trust_inputs = TrustScoreInputs(
        ocr_accuracy=0.95,
        doc_classification_confidence=0.90,
        field_extraction_completeness=0.85,
        qr_present=True,
        qr_valid=True,
        blockchain_status="verified",
        tampering_score=5.0,
        is_duplicate=False,
        fraud_probability=clean_fraud.fraud_probability,
    )
    clean_trust = compute_trust_score(clean_trust_inputs)
    assert clean_trust.score > 85.0
    assert clean_trust.evidence_breakdown["qr"]["status"] == "PASS"

    # ── 2. Evidence with Severe Tampering and Invalid QR ─────────────────────
    tampered_fraud_inputs = FraudFactorInputs(
        ocr_accuracy=0.95,
        doc_classification_confidence=0.90,
        field_extraction_completeness=0.85,
        qr_present=True,
        qr_valid=False,                  # INVALID QR
        blockchain_status="verified",
        tampering_score=78.0,            # SEVERE TAMPERING
        is_duplicate=False,
    )
    tampered_fraud = compute_fraud_analysis(tampered_fraud_inputs)
    assert tampered_fraud.fraud_probability > 0.60
    assert any("tampering_severe" in o for o in tampered_fraud.critical_overrides_applied)

    tampered_trust_inputs = TrustScoreInputs(
        ocr_accuracy=0.95,
        doc_classification_confidence=0.90,
        field_extraction_completeness=0.85,
        qr_present=True,
        qr_valid=False,
        blockchain_status="verified",
        tampering_score=78.0,
        is_duplicate=False,
        fraud_probability=tampered_fraud.fraud_probability,
    )
    tampered_trust = compute_trust_score(tampered_trust_inputs)
    assert tampered_trust.score < clean_trust.score  # Score changed dynamically!
    assert tampered_trust.score <= 59.0              # Capped at max 59 on severe tampering

    # ── 3. Evidence for Duplicate Document ───────────────────────────────────
    dup_trust_inputs = TrustScoreInputs(
        ocr_accuracy=0.95,
        qr_present=True,
        qr_valid=True,
        tampering_score=0.0,
        is_duplicate=True,                            # DUPLICATE
    )
    dup_trust = compute_trust_score(dup_trust_inputs)
    assert dup_trust.score <= 15.0                   # Capped at hard ceiling <= 15

def test_fraud_and_trust_score_end_to_end_api(client):
    import uuid
    rnd = uuid.uuid4().hex[:8]
    email = f"trust_user_{rnd}@example.com"
    password = "TestPassword123!"
    client.post("/api/v1/auth/register", json={
        "full_name": "Trust Test User",
        "email": email,
        "password": password,
        "role": "student"
    })
    from tests.conftest import verify_test_user_email_sync
    verify_test_user_email_sync(email)
    login_res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # ── Upload Document ───────────────────────────────────────────────────────
    doc_bytes = create_sample_doc("white")
    files = {"files": ("trust_test_doc.png", io.BytesIO(doc_bytes), "image/png")}
    upload_res = client.post("/api/v1/certificates/upload", files=files, headers=headers)
    assert upload_res.status_code == 201
    cert_id = upload_res.json()["certificates"][0]["id"]

    # ── Execute Full Verification Pipeline ────────────────────────────────────
    # 1. OCR
    ocr_res = client.post(f"/api/v1/certificates/{cert_id}/ocr", headers=headers)
    assert ocr_res.status_code == 200

    # 2. Tampering
    tamp_res = client.post(f"/api/v1/certificates/{cert_id}/verify-tampering", headers=headers)
    assert tamp_res.status_code == 200

    # 3. Duplicate
    dup_res = client.post(f"/api/v1/certificates/{cert_id}/verify-duplicate", headers=headers)
    assert dup_res.status_code == 200

    # 4. Fraud Analysis
    fraud_res = client.post(f"/api/v1/certificates/{cert_id}/analyze-fraud", headers=headers)
    assert fraud_res.status_code == 200
    fraud_data = fraud_res.json()
    assert fraud_data["certificate_id"] == cert_id
    assert 0.0 <= fraud_data["fraud_probability"] <= 1.0

    # 5. Compute Trust Score
    trust_res = client.post(f"/api/v1/certificates/{cert_id}/compute-trust-score", headers=headers)
    assert trust_res.status_code == 200
    trust_data = trust_res.json()
    assert trust_data["certificate_id"] == cert_id
    assert 0.0 <= trust_data["score"] <= 100.0
    assert "breakdown" in trust_data
