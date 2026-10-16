"""
Unit tests for Module 7 - AI Fraud Analysis.
Full API tests need an authenticated session with a fully-verified
certificate (see NOTE in test_upload.py). The scoring logic itself is
covered directly here — every assertion was run against the real code
during development (including catching and fixing two initially-wrong
test expectations, not the code), see the conversation this was built in.
"""
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.services.fraud_analysis import compute_fraud_analysis, FraudFactorInputs

CERT_BASE = "/api/v1/certificates"


@pytest.mark.asyncio
async def test_analyze_fraud_requires_authentication():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(f"{CERT_BASE}/00000000-0000-0000-0000-000000000000/analyze-fraud")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_fraud_analysis_requires_authentication():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(f"{CERT_BASE}/00000000-0000-0000-0000-000000000000/fraud-analysis")
    assert resp.status_code == 401


def test_clean_certificate_yields_low_fraud_probability():
    inputs = FraudFactorInputs(
        ocr_accuracy=0.95, comparison_consistency_pct=100.0, qr_present=True, qr_valid=True,
        blockchain_status="verified", tampering_score=5.0, is_duplicate=False,
        metadata_flags_present=False, image_quality_score=90.0,
    )
    result = compute_fraud_analysis(inputs)
    assert result.fraud_probability < 0.15


def test_duplicate_certificate_forces_high_floor_regardless_of_other_signals():
    inputs = FraudFactorInputs(
        ocr_accuracy=0.95, comparison_consistency_pct=100.0, qr_present=True, qr_valid=True,
        blockchain_status="verified", tampering_score=5.0, is_duplicate=True,
        metadata_flags_present=False, image_quality_score=90.0,
    )
    result = compute_fraud_analysis(inputs)
    assert result.fraud_probability >= 0.85


def test_worst_case_all_bad_signals_plus_duplicate():
    inputs = FraudFactorInputs(
        ocr_accuracy=0.4, comparison_consistency_pct=20.0, qr_present=True, qr_valid=False,
        blockchain_status="mismatch", tampering_score=85.0, is_duplicate=True,
        metadata_flags_present=True, image_quality_score=30.0,
    )
    result = compute_fraud_analysis(inputs)
    assert result.fraud_probability >= 0.85


def test_unavailable_blockchain_is_excluded_not_penalized():
    inputs = FraudFactorInputs(
        ocr_accuracy=0.9, qr_present=True, qr_valid=True,
        blockchain_status="unavailable", tampering_score=10.0, is_duplicate=False,
    )
    result = compute_fraud_analysis(inputs)
    assert result.factor_weights["blockchain"] == 0.0
    assert abs(sum(result.factor_weights.values()) - 1.0) < 0.001  # remaining weights renormalize to 1


def test_no_signals_available_returns_neutral_probability():
    result = compute_fraud_analysis(FraudFactorInputs())
    assert result.fraud_probability == 0.5
    assert result.factor_weights == {}


def test_missing_qr_is_mild_not_severe_risk():
    """Per Module 6 spec: a missing QR generates a warning, not a hard fail."""
    with_qr = FraudFactorInputs(qr_present=True, qr_valid=True)
    without_qr = FraudFactorInputs(qr_present=False)

    result_with = compute_fraud_analysis(with_qr)
    result_without = compute_fraud_analysis(without_qr)

    assert result_without.fraud_probability > result_with.fraud_probability
    assert result_without.fraud_probability < 0.3  # mild, not severe
