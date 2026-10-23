"""
Regression tests for Verification Pipeline Telemetry & Certificate UUID normalization.

Ensures:
1. GET /api/v1/certificates/{id}/pipeline returns 200 with all 14 registered stages.
2. Certificate lookups resolve transparently whether requested with hyphens or without.
3. Newly uploaded certificates report correct initial stage states without throwing 500.
4. Fully processed certificates reach FULLY_COMPLETE with 100% completion.
5. All stages have explainable status and summary metadata.
"""
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.db.database import AsyncSessionLocal
from app.models.models import (
    User, Certificate, UserRole, OCRData, DocumentType,
    VerificationResult, FraudAnalysis, TrustScore, FinalPrediction,
    VerificationReport, DocTypeEnum, PredictionLabel,
)
from app.core.security import create_access_token


@pytest_asyncio.fixture
async def regression_test_context():
    """Creates a dedicated test user and certificate in the test database."""
    user_hex = uuid.uuid4().hex
    cert_hex = uuid.uuid4().hex
    cert_uuid_obj = uuid.UUID(cert_hex)
    cert_with_dashes = str(cert_uuid_obj)

    async with AsyncSessionLocal() as session:
        user = User(
            id=user_hex,
            email=f"reg_{user_hex[:8]}@example.com",
            full_name="Regression Test User",
            hashed_password="test_hashed_password",
            role=UserRole.STUDENT,
            is_active=True,
            is_email_verified=True,
        )
        session.add(user)

        cert = Certificate(
            id=cert_hex,
            owner_id=user_hex,
            original_filename="regression_cert.pdf",
            storage_path=f"/tmp/test_certs/{cert_hex}.pdf",
            file_type="pdf",
            file_size_bytes=1024,
            sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            uploaded_at=datetime.now(timezone.utc),
        )
        session.add(cert)
        await session.commit()

    token = create_access_token(subject=user_hex, extra_claims={"role": "student"})
    headers = {"Authorization": f"Bearer {token}"}

    yield {
        "user_id": user_hex,
        "cert_id_hex": cert_hex,
        "cert_id_dashes": cert_with_dashes,
        "headers": headers,
    }


EXPECTED_STAGE_KEYS = [
    "upload",
    "ocr",
    "classification",
    "field_extraction",
    "comparison",
    "qr_verification",
    "hash_check",
    "blockchain",
    "tampering",
    "duplicate",
    "fraud_analysis",
    "trust_score",
    "prediction",
    "report",
]


@pytest.mark.asyncio
async def test_pipeline_returns_all_14_stages_with_hyphenated_uuid(regression_test_context):
    ctx = regression_test_context
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            f"/api/v1/certificates/{ctx['cert_id_dashes']}/pipeline",
            headers=ctx["headers"],
        )

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()

    assert data["certificate_id"] in (ctx["cert_id_hex"], ctx["cert_id_dashes"])
    assert data["filename"] == "regression_cert.pdf"
    assert "stages" in data
    assert len(data["stages"]) == 14, f"Expected 14 stages, got {len(data['stages'])}"

    returned_keys = [s["stage"] for s in data["stages"]]
    assert returned_keys == EXPECTED_STAGE_KEYS


@pytest.mark.asyncio
async def test_pipeline_uuid_format_parity(regression_test_context):
    ctx = regression_test_context
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res_dashes = await ac.get(
            f"/api/v1/certificates/{ctx['cert_id_dashes']}/pipeline",
            headers=ctx["headers"],
        )
        res_hex = await ac.get(
            f"/api/v1/certificates/{ctx['cert_id_hex']}/pipeline",
            headers=ctx["headers"],
        )

    assert res_dashes.status_code == 200
    assert res_hex.status_code == 200

    d_dashes = res_dashes.json()
    d_hex = res_hex.json()

    assert d_dashes["completion_pct"] == d_hex["completion_pct"]
    assert d_dashes["overall_status"] == d_hex["overall_status"]
    assert len(d_dashes["stages"]) == len(d_hex["stages"]) == 14


@pytest.mark.asyncio
async def test_fresh_certificate_initial_stages(regression_test_context):
    ctx = regression_test_context
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            f"/api/v1/certificates/{ctx['cert_id_dashes']}/pipeline",
            headers=ctx["headers"],
        )

    assert resp.status_code == 200
    data = resp.json()

    stage_map = {s["stage"]: s for s in data["stages"]}
    assert stage_map["upload"]["status"] == "COMPLETED"
    assert stage_map["ocr"]["status"] == "PENDING"
    assert stage_map["prediction"]["status"] == "PENDING"
    assert stage_map["report"]["status"] == "PENDING"


@pytest.mark.asyncio
async def test_fully_processed_certificate_reaches_completion(regression_test_context):
    ctx = regression_test_context
    cert_id = ctx["cert_id_hex"]

    async with AsyncSessionLocal() as session:
        # 1. OCR Data
        ocr = OCRData(
            certificate_id=cert_id,
            student_name="Test Student",
            university_name="Test University",
            register_number="REG123456",
            raw_text="Test Student REG123456 Test University",
            ocr_accuracy=0.96,
            ocr_engine="easyocr+tesseract",
            field_confidences={"student_name": 0.95, "register_number": 0.95},
        )
        session.add(ocr)

        # 2. DocumentType
        dt = DocumentType(
            certificate_id=cert_id,
            predicted_type=DocTypeEnum.DEGREE_CERTIFICATE,
            confidence_score=0.95,
            model_used="rule-ocr-fused",
        )
        session.add(dt)

        # 3. Verification Result
        vr = VerificationResult(
            certificate_id=cert_id,
            qr_present=True,
            qr_valid=True,
            qr_decoded_data={"certificate_id": cert_id, "_qr_type": "URL"},
            blockchain_status="skipped",
            tampering_score=5.0,
            tampering_risk_level="LOW",
            is_duplicate=False,
            duplicate_match_reason="No duplicate found",
            hash_match_status="MATCH",
        )
        session.add(vr)

        # 4. Fraud Analysis
        fa = FraudAnalysis(
            certificate_id=cert_id,
            fraud_probability=0.05,
            ocr_accuracy_weight=0.15,
            comparison_weight=0.15,
            qr_weight=0.10,
            blockchain_weight=0.15,
            tampering_weight=0.20,
            duplicate_weight=0.10,
            metadata_integrity_weight=0.05,
            image_quality_weight=0.10,
        )
        session.add(fa)

        # 5. Trust Score
        ts = TrustScore(
            certificate_id=cert_id,
            score=94.5,
            breakdown={"overall": 94.5},
        )
        session.add(ts)

        # 6. Final Prediction
        fp = FinalPrediction(
            certificate_id=cert_id,
            label=PredictionLabel.GENUINE,
            confidence_score=0.95,
            explanation="All core signals verified genuine.",
            recommended_action="ACCEPT",
        )
        session.add(fp)

        # 7. Verification Report
        vr_rep = VerificationReport(
            certificate_id=cert_id,
            verification_id="CV-2026-TEST",
            pdf_path="/tmp/test_report.pdf",
            digital_signature="sig123",
        )
        session.add(vr_rep)

        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            f"/api/v1/certificates/{ctx['cert_id_dashes']}/pipeline",
            headers=ctx["headers"],
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["overall_status"] == "FULLY_COMPLETE"
    assert data["completion_pct"] == 100.0


@pytest.mark.asyncio
async def test_non_existent_certificate_returns_404(regression_test_context):
    ctx = regression_test_context
    missing_id = "00000000-0000-0000-0000-000000000099"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            f"/api/v1/certificates/{missing_id}/pipeline",
            headers=ctx["headers"],
        )

    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()
