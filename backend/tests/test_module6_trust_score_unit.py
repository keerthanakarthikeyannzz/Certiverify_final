"""
Unit tests for MODULE 6: Trust Score stage (trust_score)

Tests:
1. Monotonicity: adding verified positive evidence never lowers the score
2. Exclusion and renormalization of 'not evaluated' components (not treated as zero)
3. Breakdown schema (value, weight, contribution, status, reason)
4. Coverage calculation (evaluated / 8)
5. Score bands (HIGH, MEDIUM, LOW) from settings
6. Hard ceilings for critical fraud evidence (blockchain mismatch, duplicate collision, severe tampering)
7. Same-owner duplicate is benign and maintains high trust
"""
import pytest
from app.services.trust_score import (
    TrustScoreInputs,
    compute_trust_score,
    get_nominal_trust_weights,
    TRUST_COMPONENT_KEYS,
)


def test_nominal_weights_sum_to_one():
    weights = get_nominal_trust_weights()
    assert len(weights) == 8
    for k in TRUST_COMPONENT_KEYS:
        assert k in weights
        assert weights[k] > 0
    assert abs(sum(weights.values()) - 1.0) < 1e-4


def test_monotonicity_more_verified_evidence_never_lowers_score():
    """
    Mathematical monotonicity test:
    Adding verified evidence (e.g. verified QR, verified blockchain, clean uniqueness)
    must NEVER lower the trust score.
    """
    # Base document with partial evidence (OCR and clean image quality only)
    base_inputs = TrustScoreInputs(
        ocr_accuracy=0.92,
        image_quality_score=90.0,
        # QR, Blockchain, Tampering, Duplicate, Fraud, Comparison are not evaluated
    )
    base_res = compute_trust_score(base_inputs)
    assert base_res.checks_evaluated == 2
    assert base_res.coverage == 0.25
    initial_score = base_res.score

    # Add verified QR code evidence (value = 100)
    with_qr_inputs = TrustScoreInputs(
        ocr_accuracy=0.92,
        image_quality_score=90.0,
        qr_present=True,
        qr_valid=True,
    )
    with_qr_res = compute_trust_score(with_qr_inputs)
    assert with_qr_res.checks_evaluated == 3
    assert with_qr_res.coverage == 0.375
    # Must NOT decrease
    assert with_qr_res.score >= initial_score

    # Add verified blockchain ledger match (value = 100)
    with_bc_inputs = TrustScoreInputs(
        ocr_accuracy=0.92,
        image_quality_score=90.0,
        qr_present=True,
        qr_valid=True,
        blockchain_status="verified",
        blockchain_match=True,
    )
    with_bc_res = compute_trust_score(with_bc_inputs)
    assert with_bc_res.checks_evaluated == 4
    assert with_bc_res.coverage == 0.50
    # Must NOT decrease
    assert with_bc_res.score >= with_qr_res.score

    # Add verified uniqueness (no duplicate collision, value = 100)
    with_dup_inputs = TrustScoreInputs(
        ocr_accuracy=0.92,
        image_quality_score=90.0,
        qr_present=True,
        qr_valid=True,
        blockchain_status="verified",
        blockchain_match=True,
        is_duplicate=False,
    )
    with_dup_res = compute_trust_score(with_dup_inputs)
    assert with_dup_res.checks_evaluated == 5
    assert with_dup_res.coverage == 0.625
    assert with_dup_res.score >= with_bc_res.score


def test_unavailable_components_are_not_evaluated_and_excluded():
    """
    Unavailable components must be listed as 'not evaluated', have effective weight 0.0,
    and must NOT be treated as 0 (which would drag down the score).
    """
    inputs = TrustScoreInputs(
        ocr_accuracy=0.95,
        tampering_score=5.0, # 95 trust
        # QR, Blockchain, Duplicate, Comparison, Fraud, Image Quality are None
    )
    res = compute_trust_score(inputs)

    assert res.checks_evaluated == 2
    assert res.checks_total == 8
    assert res.coverage == 0.25
    assert res.coverage_percentage == 25.0

    # Effective weights of the 2 active components must sum to 1.0
    active_weights = [c.weight for c in res.components if c.status != "not evaluated"]
    assert len(active_weights) == 2
    assert abs(sum(active_weights) - 1.0) < 1e-3

    # Unavailable components must have weight 0.0 and contribution 0.0
    qr_comp = next(c for c in res.components if c.component == "qr")
    assert qr_comp.status == "not evaluated"
    assert qr_comp.value is None
    assert qr_comp.weight == 0.0
    assert qr_comp.contribution == 0.0
    assert "not evaluated" in qr_comp.reason.lower()

    bc_comp = next(c for c in res.components if c.component == "blockchain")
    assert bc_comp.status == "not evaluated"
    assert bc_comp.value is None
    assert bc_comp.weight == 0.0
    assert bc_comp.contribution == 0.0

    # Score must be high (~95), NOT dragging down due to missing checks
    assert res.score >= 90.0
    assert res.band == "HIGH"


def test_coverage_metric_distinguishability():
    """
    Distinguishes a high score with low coverage (e.g. 2 of 8)
    from a high score with full coverage (8 of 8).
    """
    # 2 of 8 checks
    res_partial = compute_trust_score(TrustScoreInputs(
        ocr_accuracy=0.98,
        tampering_score=2.0,
    ))
    assert res_partial.checks_evaluated == 2
    assert res_partial.coverage == 0.25
    assert res_partial.score >= 95.0

    # 8 of 8 checks
    res_full = compute_trust_score(TrustScoreInputs(
        ocr_accuracy=0.98,
        tampering_score=2.0,
        qr_present=True,
        qr_valid=True,
        blockchain_status="verified",
        blockchain_match=True,
        is_duplicate=False,
        fraud_probability=0.03,
        document_consistency_pct=99.0,
        image_quality_score=95.0,
    ))
    assert res_full.checks_evaluated == 8
    assert res_full.coverage == 1.0
    assert res_full.score >= 95.0

    # Coverage clearly differentiates the two
    assert res_partial.coverage < res_full.coverage
    assert res_partial.breakdown["coverage"]["evaluated"] == 2
    assert res_full.breakdown["coverage"]["evaluated"] == 8


def test_score_bands_from_settings():
    # High Trust (>= 80)
    res_high = compute_trust_score(TrustScoreInputs(
        ocr_accuracy=0.95,
        tampering_score=5.0,
        is_duplicate=False,
    ))
    assert res_high.score >= 80.0
    assert res_high.band == "HIGH"
    assert res_high.band_label == "High Trust"

    # Medium Trust (50 - 79.9)
    res_med = compute_trust_score(TrustScoreInputs(
        ocr_accuracy=0.65,
        tampering_score=40.0,
        image_quality_score=60.0,
        fraud_probability=0.35,
    ))
    assert 50.0 <= res_med.score < 80.0
    assert res_med.band == "MEDIUM"
    assert res_med.band_label == "Medium Trust"

    # Low Trust (< 50)
    res_low = compute_trust_score(TrustScoreInputs(
        ocr_accuracy=0.30,
        tampering_score=75.0,
        fraud_probability=0.80,
    ))
    assert res_low.score < 50.0
    assert res_low.band == "LOW"
    assert res_low.band_label == "Low Trust"


def test_hard_ceiling_blockchain_mismatch():
    inputs = TrustScoreInputs(
        ocr_accuracy=0.99,
        tampering_score=1.0,
        image_quality_score=98.0,
        blockchain_status="mismatch",
        blockchain_match=False,
    )
    res = compute_trust_score(inputs)
    # Floor must cap at 49.0
    assert res.score <= 49.0
    assert res.band in ("LOW", "MEDIUM")
    assert any("blockchain_mismatch_ceiling" in c for c in res.hard_ceilings_applied)


def test_hard_ceiling_different_owner_duplicate():
    inputs = TrustScoreInputs(
        ocr_accuracy=0.98,
        tampering_score=2.0,
        is_duplicate=True,
        duplicate_same_owner=False,
        duplicate_detail={"same_owner": False, "owner_distinction": "DIFFERENT_OWNER_DUPLICATE"}
    )
    res = compute_trust_score(inputs)
    # Severe duplicate collision caps at 15.0
    assert res.score <= 15.0
    assert res.band == "LOW"
    assert any("different_owner_duplicate_ceiling" in c for c in res.hard_ceilings_applied)


def test_same_owner_duplicate_is_benign():
    inputs = TrustScoreInputs(
        ocr_accuracy=0.95,
        tampering_score=5.0,
        is_duplicate=True,
        duplicate_same_owner=True,
        duplicate_detail={"same_owner": True, "owner_distinction": "SAME_OWNER_REUPLOAD"}
    )
    res = compute_trust_score(inputs)
    # Same owner re-upload should NOT trigger ceiling and must remain high trust
    assert res.score >= 85.0
    assert not any("different_owner_duplicate" in c for c in res.hard_ceilings_applied)
    assert res.band == "HIGH"
