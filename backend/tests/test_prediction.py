"""
Unit tests for Module 9 - Final Prediction.
Full API tests need an authenticated session with a certificate that has
a Trust Score already computed (see NOTE in test_upload.py). The
classification logic itself is covered directly here — every assertion
was run against the real code during development, including the boundary
edge cases (79.9 vs 80.0, 49.9 vs 50.0) and the completeness-lowers-
confidence behavior, before being written up as formal tests.
"""
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.services.final_prediction import predict, PredictionInputs

CERT_BASE = "/api/v1/certificates"


@pytest.mark.asyncio
async def test_predict_requires_authentication():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(f"{CERT_BASE}/00000000-0000-0000-0000-000000000000/predict")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_prediction_requires_authentication():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(f"{CERT_BASE}/00000000-0000-0000-0000-000000000000/prediction")
    assert resp.status_code == 401


def test_high_trust_score_yields_confident_genuine():
    result = predict(PredictionInputs(
        trust_score=97.85, data_completeness=1.0, is_duplicate=False,
        tampering_score=3.0, blockchain_status="verified", qr_present=True, qr_valid=True,
        comparison_consistency_pct=100.0, fraud_probability=0.02, ocr_accuracy=0.96,
    ))
    assert result.label == "genuine"
    assert result.confidence > 0.7
    assert "Trust Score" in result.explanation


def test_mid_trust_score_yields_suspicious():
    result = predict(PredictionInputs(
        trust_score=74.5, data_completeness=1.0, is_duplicate=False,
        tampering_score=25.0, blockchain_status="not_found", qr_present=True, qr_valid=True,
        comparison_consistency_pct=70.0, fraud_probability=0.35, ocr_accuracy=0.75,
    ))
    assert result.label == "suspicious"


def test_low_trust_score_yields_fake():
    result = predict(PredictionInputs(
        trust_score=27.25, data_completeness=1.0, is_duplicate=False,
        tampering_score=90.0, blockchain_status="mismatch", qr_present=True, qr_valid=False,
        comparison_consistency_pct=20.0, fraud_probability=0.7, ocr_accuracy=0.4,
    ))
    assert result.label == "fake"
    assert result.confidence > 0.5


def test_duplicate_forces_fake_regardless_of_score():
    result = predict(PredictionInputs(trust_score=95.0, data_completeness=1.0, is_duplicate=True))
    assert result.label == "fake"
    assert result.confidence >= 0.9
    assert "duplicate" in result.recommended_action.lower()


def test_threshold_boundaries_are_exact():
    assert predict(PredictionInputs(trust_score=80.0, data_completeness=1.0)).label == "genuine"
    assert predict(PredictionInputs(trust_score=79.9, data_completeness=1.0)).label == "suspicious"
    assert predict(PredictionInputs(trust_score=50.0, data_completeness=1.0)).label == "suspicious"
    assert predict(PredictionInputs(trust_score=49.9, data_completeness=1.0)).label == "fake"


def test_low_data_completeness_reduces_confidence_at_same_score():
    low_completeness = predict(PredictionInputs(trust_score=97.0, data_completeness=0.2))
    full_completeness = predict(PredictionInputs(trust_score=97.0, data_completeness=1.0))
    assert low_completeness.confidence < full_completeness.confidence


def test_recommended_action_differs_by_label():
    genuine = predict(PredictionInputs(trust_score=95.0, data_completeness=1.0))
    suspicious = predict(PredictionInputs(trust_score=65.0, data_completeness=1.0))
    fake = predict(PredictionInputs(trust_score=20.0, data_completeness=1.0))
    assert genuine.recommended_action != suspicious.recommended_action != fake.recommended_action
