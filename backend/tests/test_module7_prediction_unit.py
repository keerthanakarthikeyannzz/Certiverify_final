"""
Unit Tests for MODULE 7: Final Prediction Stage (prediction)

Validates:
1. Decision function combining fraud_probability, trust score, coverage, and hard overrides.
2. Low evidence coverage (< 50% / < 4 of 8 checks) gate forcing INCONCLUSIVE.
3. Plain-language explanation detailing which checks passed, which failed, and which were not evaluated.
4. Recommended action mapping from settings per label (genuine, suspicious, fake, inconclusive).
5. Decision support advisory notice.
6. Hard overrides (blockchain mismatch, duplicate collision, severe tampering >= 70) forcing FAKE.
"""
import pytest
from app.core.config import settings
from app.services.final_prediction import predict, PredictionInputs, PredictionResult


def test_genuine_high_trust_low_fraud_high_coverage():
    """
    Test genuine document with high trust score (>=80), low fraud (<=0.25), and high coverage (>=50%).
    """
    inputs = PredictionInputs(
        trust_score=92.5,
        coverage=0.875,
        checks_evaluated=7,
        checks_total=8,
        fraud_probability=0.05,
        ocr_accuracy=0.96,
        tampering_score=4.0,
        tampering_status="analyzed",
        is_duplicate=False,
        qr_present=True,
        qr_valid=True,
        blockchain_status="verified",
        blockchain_match=True,
        image_quality_score=90.0,
    )
    res = predict(inputs)
    assert res.label == "genuine"
    assert res.confidence >= 0.80
    assert "GENUINE" in res.explanation
    assert res.recommended_action == settings.PREDICTION_ACTION_GENUINE
    assert len(res.passed_checks) >= 5
    assert len(res.failed_checks) == 0
    # Must list passed checks
    assert any("OCR text extraction" in p for p in res.passed_checks)
    assert any("QR Code cryptographic signature" in p for p in res.passed_checks)
    assert any("Blockchain ledger" in p for p in res.passed_checks)


def test_inconclusive_low_coverage_gate():
    """
    Test requirement 2: Low evidence coverage (< 50% / < 4 of 8 checks evaluated)
    forces INCONCLUSIVE even if trust score is high.
    """
    inputs = PredictionInputs(
        trust_score=90.0,
        coverage=0.25, # 2 of 8 checks
        checks_evaluated=2,
        checks_total=8,
        fraud_probability=0.08,
        ocr_accuracy=0.92,
        is_duplicate=False,
        # QR, Blockchain, Tampering, Comparison, Image Quality NOT evaluated
    )
    res = predict(inputs)
    assert res.label == "inconclusive"
    assert res.recommended_action == settings.PREDICTION_ACTION_INCONCLUSIVE
    assert "INCONCLUSIVE" in res.explanation
    assert "below the required" in res.reasons[0]
    # Check that not evaluated checks are detailed
    assert len(res.not_evaluated_checks) >= 5
    assert any("QR Verification" in n for n in res.not_evaluated_checks)
    assert any("Blockchain Verification" in n for n in res.not_evaluated_checks)
    assert any("Tampering analysis" in n for n in res.not_evaluated_checks)


def test_suspicious_moderate_risk_indicators():
    """
    Test moderate trust score (50-79.9) or moderate fraud probability (0.26-0.60) yields SUSPICIOUS.
    """
    inputs = PredictionInputs(
        trust_score=62.0,
        coverage=0.75, # 6 of 8 checks
        checks_evaluated=6,
        checks_total=8,
        fraud_probability=0.38,
        ocr_accuracy=0.72,
        tampering_score=35.0, # moderate
        tampering_status="analyzed",
        is_duplicate=False,
        qr_present=True,
        qr_valid=True,
        blockchain_status="not_found",
    )
    res = predict(inputs)
    assert res.label == "suspicious"
    assert res.recommended_action == settings.PREDICTION_ACTION_SUSPICIOUS
    assert "SUSPICIOUS" in res.explanation
    # Decision support advisory notice must be in explanation
    assert "human compliance officer" in res.explanation.lower()


def test_hard_override_blockchain_mismatch_forces_fake():
    """
    Cryptographic blockchain mismatch is incontrovertible forgery -> forces FAKE.
    """
    inputs = PredictionInputs(
        trust_score=45.0,
        coverage=0.625,
        checks_evaluated=5,
        checks_total=8,
        fraud_probability=0.88,
        blockchain_status="mismatch",
        blockchain_match=False,
        ocr_accuracy=0.85,
        is_duplicate=False,
        tampering_score=15.0,
    )
    res = predict(inputs)
    assert res.label == "fake"
    assert res.confidence >= 0.90
    assert res.recommended_action == settings.PREDICTION_ACTION_FAKE
    assert any("Blockchain cryptographic hash MISMATCH" in f for f in res.failed_checks)


def test_hard_override_duplicate_collision_forces_fake():
    """
    Credential duplicate collision with another user forces FAKE.
    """
    inputs = PredictionInputs(
        trust_score=30.0,
        coverage=0.75,
        checks_evaluated=6,
        checks_total=8,
        fraud_probability=0.90,
        is_duplicate=True,
        duplicate_same_owner=False,
        duplicate_status="duplicate_found",
        duplicate_detail={"same_owner": False, "owner_distinction": "DIFFERENT_OWNER_COLLISION"},
    )
    res = predict(inputs)
    assert res.label == "fake"
    assert res.confidence >= 0.90
    assert any("Duplicate credential collision" in f for f in res.failed_checks)


def test_hard_override_severe_tampering_forces_fake():
    """
    Tampering score >= 70 forces FAKE.
    """
    inputs = PredictionInputs(
        trust_score=35.0,
        coverage=0.625,
        checks_evaluated=5,
        checks_total=8,
        fraud_probability=0.80,
        tampering_score=78.5,
        tampering_status="analyzed",
        is_duplicate=False,
    )
    res = predict(inputs)
    assert res.label == "fake"
    assert any("Severe tampering detected" in f for f in res.failed_checks)


def test_explanation_categorization_integrity():
    """
    Verify plain-language explanation includes verified positive evidence,
    identified risk signals/failures, and not evaluated checks without fabricating unsupported claims.
    """
    inputs = PredictionInputs(
        trust_score=85.0,
        coverage=0.625,
        checks_evaluated=5,
        checks_total=8,
        fraud_probability=0.15,
        ocr_accuracy=0.95,
        tampering_score=12.0,
        tampering_status="analyzed",
        is_duplicate=False,
        qr_present=False, # no QR on document
        blockchain_status="not_applicable", # unconfigured
        comparison_consistency_pct=None, # not evaluated
    )
    res = predict(inputs)
    assert "Verified Positive Evidence:" in res.explanation
    assert "OCR text extraction" in res.explanation
    assert "Tampering & ELA scan clean" in res.explanation
    assert "Checks Excluded / Not Evaluated:" in res.explanation
    assert "QR Verification (no QR code on document)" in res.explanation
    assert "Blockchain Verification" in res.explanation
