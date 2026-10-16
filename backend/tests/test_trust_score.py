"""
Unit tests for Module 8 - Trust Score Engine.
Full API tests need an authenticated session with a fully-analyzed
certificate (see NOTE in test_upload.py). The scoring logic itself is
covered directly here — every assertion was run against the real code
during development (including catching one initially-wrong test
expectation caused by the same "clean single factor legitimately drags
up a bad average" pattern seen in Module 7's tests).
"""
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.services.trust_score import compute_trust_score, TrustScoreInputs

CERT_BASE = "/api/v1/certificates"


@pytest.mark.asyncio
async def test_compute_trust_score_requires_authentication():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(f"{CERT_BASE}/00000000-0000-0000-0000-000000000000/compute-trust-score")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_trust_score_requires_authentication():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(f"{CERT_BASE}/00000000-0000-0000-0000-000000000000/trust-score")
    assert resp.status_code == 401


def test_clean_certificate_scores_in_genuine_range():
    inputs = TrustScoreInputs(
        ocr_accuracy=0.96, image_quality_score=90.0, document_consistency_pct=100.0,
        blockchain_status="verified", qr_present=True, qr_valid=True,
        tampering_score=3.0, is_duplicate=False, fraud_probability=0.02,
    )
    result = compute_trust_score(inputs)
    assert result.score >= 85  # comfortably above the spec's ~95 "Genuine" example


def test_duplicate_certificate_hard_capped_at_15():
    inputs = TrustScoreInputs(
        ocr_accuracy=0.96, image_quality_score=90.0, document_consistency_pct=100.0,
        blockchain_status="verified", qr_present=True, qr_valid=True,
        tampering_score=3.0, is_duplicate=True, fraud_probability=0.02,
    )
    result = compute_trust_score(inputs)
    assert result.score <= 15


def test_mid_quality_certificate_lands_in_suspicious_band():
    inputs = TrustScoreInputs(
        ocr_accuracy=0.75, image_quality_score=65.0, document_consistency_pct=70.0,
        blockchain_status="not_found", qr_present=True, qr_valid=True,
        tampering_score=25.0, is_duplicate=False, fraud_probability=0.35,
    )
    result = compute_trust_score(inputs)
    assert 50 <= result.score < 80  # between the spec's ~72 "Suspicious" and ~95 "Genuine" examples


def test_worst_case_with_duplicate_scores_in_fake_range():
    inputs = TrustScoreInputs(
        ocr_accuracy=0.4, image_quality_score=25.0, document_consistency_pct=20.0,
        blockchain_status="mismatch", qr_present=True, qr_valid=False,
        tampering_score=90.0, is_duplicate=True, fraud_probability=0.85,
    )
    result = compute_trust_score(inputs)
    assert result.score <= 20  # below the spec's ~40 "Fake" example


def test_unavailable_blockchain_excluded_and_weights_renormalize():
    inputs = TrustScoreInputs(ocr_accuracy=0.9, blockchain_status="unavailable", is_duplicate=False)
    result = compute_trust_score(inputs)
    assert result.breakdown["blockchain"] == 0.0
    assert abs(sum(result.breakdown.values()) - 1.0) < 0.001


def test_no_data_returns_neutral_fifty():
    result = compute_trust_score(TrustScoreInputs())
    assert result.score == 50.0
    assert result.breakdown == {}
