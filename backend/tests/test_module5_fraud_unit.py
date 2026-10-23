"""
Unit tests for MODULE 5: AI Fraud Analysis (fraud_analysis)
Tests:
1. Signal normalizers (0-1 range and proper mapping)
2. Weight exclusion and renormalization when signals are missing/NOT_APPLICABLE
3. Hard floor overrides (blockchain mismatch, duplicate collision, severe tampering)
4. Same-owner duplicate is benign and does NOT trigger hard floors
5. Image quality analysis (blur, resolution, contrast)
6. Clean vs edited document comparison
7. Per-signal contributions explainability
"""
import pytest
import numpy as np

from app.services.fraud_analysis import (
    FraudFactorInputs,
    compute_fraud_analysis,
    normalize_ocr_accuracy,
    normalize_comparison,
    normalize_qr,
    normalize_blockchain,
    normalize_tampering,
    normalize_duplicate,
    normalize_metadata_integrity,
    normalize_image_quality,
    get_nominal_weights,
    SIGNAL_KEYS,
)
from app.services.image_quality import compute_image_quality_details


def test_nominal_weights_sum_to_one():
    weights = get_nominal_weights()
    assert len(weights) == 8
    for k in SIGNAL_KEYS:
        assert k in weights
        assert weights[k] > 0
    assert abs(sum(weights.values()) - 1.0) < 1e-4


def test_ocr_normalizer():
    # Perfect accuracy -> low risk
    risk, det = normalize_ocr_accuracy(0.98, {"name": 0.99, "reg": 0.97})
    assert risk is not None
    assert risk < 0.05

    # Low accuracy -> high risk
    risk_low, _ = normalize_ocr_accuracy(0.30, {"name": 0.20})
    assert risk_low > 0.70

    # Missing accuracy -> None (excluded)
    risk_none, _ = normalize_ocr_accuracy(None, None)
    assert risk_none is None


def test_comparison_normalizer():
    # 100% consistent -> 0.0 risk
    risk, _ = normalize_comparison(100.0)
    assert risk == 0.0

    # 40% consistent -> 0.6 risk
    risk_low, _ = normalize_comparison(40.0)
    assert risk_low == 0.60

    # Missing -> None (excluded)
    risk_none, _ = normalize_comparison(None)
    assert risk_none is None


def test_qr_normalizer():
    # Valid QR -> 0.0 risk
    risk, _ = normalize_qr(present=True, valid=True, warning=None)
    assert risk == 0.0

    # Invalid QR -> high risk
    risk_bad, _ = normalize_qr(present=True, valid=False, warning="Signature invalid")
    assert risk_bad == 0.85

    # No QR present -> None (excluded, not penalized)
    risk_no_qr, _ = normalize_qr(present=False, valid=None, warning=None)
    assert risk_no_qr is None


def test_blockchain_normalizer():
    # Verified -> 0.0 risk
    risk, _ = normalize_blockchain("verified", True)
    assert risk == 0.0

    # Mismatch -> 1.0 risk
    risk_mis, _ = normalize_blockchain("mismatch", False)
    assert risk_mis == 1.0

    # Not found -> neutral unanchored
    risk_nf, _ = normalize_blockchain("not_found", None)
    assert risk_nf == 0.35

    # Unavailable / None -> None (excluded)
    risk_un, _ = normalize_blockchain("unavailable", None)
    assert risk_un is None


def test_duplicate_normalizer_owner_distinction():
    # Same owner re-upload -> 0.0 risk (benign)
    risk_own, _ = normalize_duplicate(
        is_duplicate=True,
        detail={"same_owner": True, "duplicate_type": "EXACT_FILE_DUPLICATE", "owner_distinction": "SAME_OWNER_REUPLOAD"}
    )
    assert risk_own == 0.0

    # Different owner exact duplicate -> 0.90 risk
    risk_diff, _ = normalize_duplicate(
        is_duplicate=True,
        detail={"same_owner": False, "duplicate_type": "EXACT_FILE_DUPLICATE", "owner_distinction": "DIFFERENT_OWNER_DUPLICATE"}
    )
    assert risk_diff == 0.90

    # Identity conflict -> 1.0 risk
    risk_conf, _ = normalize_duplicate(
        is_duplicate=True,
        detail={"duplicate_type": "CERTIFICATE_CONFLICT"}
    )
    assert risk_conf == 1.0

    # Not a duplicate -> 0.0 risk
    risk_clean, _ = normalize_duplicate(is_duplicate=False, detail={})
    assert risk_clean == 0.0


def test_metadata_normalizer():
    # Clean metadata -> 0.0 risk
    risk_clean, _ = normalize_metadata_integrity(flags=[], flags_present=False)
    assert risk_clean == 0.0

    # Photoshop editing tool detected -> high risk
    risk_photo, _ = normalize_metadata_integrity(flags=["Software: Adobe Photoshop 2024", "Incremental updates"], flags_present=True)
    assert risk_photo >= 0.70


def test_image_quality_details():
    # Crisp high-contrast synthetic image
    img = np.zeros((1000, 800, 3), dtype=np.uint8)
    img[::10, :] = 255
    img[:, ::10] = 255

    details = compute_image_quality_details(img)
    assert details["overall_score"] > 60.0
    assert details["risk"] < 0.40
    assert "sharpness_score" in details
    assert "resolution_score" in details
    assert "contrast_score" in details


def test_weight_renormalization_missing_signals():
    # Only 3 signals available: OCR, Tampering, and Image Quality
    inputs = FraudFactorInputs(
        ocr_accuracy=0.96,
        tampering_score=10.0,
        image_quality_score=90.0,
        # QR, Blockchain, Comparison, Duplicate, Metadata are missing/excluded
    )
    result = compute_fraud_analysis(inputs)

    # Active weights must sum to 1.0
    active_weights = [w for w in result.factor_weights.values() if w > 0]
    assert len(active_weights) == 3
    assert abs(sum(active_weights) - 1.0) < 1e-3

    # Excluded signals must have 0.0 effective weight
    assert result.factor_weights["comparison"] == 0.0
    assert result.factor_weights["blockchain"] == 0.0
    assert result.factor_weights["qr"] == 0.0
    assert result.factor_weights["duplicate"] == 0.0

    # Status must be CLEAN and probability low
    assert result.risk_level == "LOW"
    assert result.fraud_probability < 0.20


def test_hard_override_blockchain_mismatch():
    inputs = FraudFactorInputs(
        ocr_accuracy=0.98,
        tampering_score=5.0,
        image_quality_score=95.0,
        blockchain_status="mismatch",
        blockchain_match=False,
    )
    result = compute_fraud_analysis(inputs)

    # Floor at 0.85 must fire despite clean OCR and clean tampering
    assert result.fraud_probability >= 0.85
    assert any("blockchain_mismatch_floor" in ov for ov in result.critical_overrides_applied)
    assert result.risk_level == "VERY_HIGH"


def test_hard_override_different_owner_duplicate():
    inputs = FraudFactorInputs(
        ocr_accuracy=0.95,
        tampering_score=8.0,
        image_quality_score=90.0,
        is_duplicate=True,
        duplicate_detail={
            "same_owner": False,
            "duplicate_type": "EXACT_FILE_DUPLICATE",
            "owner_distinction": "DIFFERENT_OWNER_DUPLICATE"
        }
    )
    result = compute_fraud_analysis(inputs)

    # Floor at 0.85 must fire
    assert result.fraud_probability >= 0.85
    assert any("different_owner_duplicate_floor" in ov for ov in result.critical_overrides_applied)
    assert result.risk_level == "VERY_HIGH"


def test_same_owner_duplicate_does_not_fire_override():
    inputs = FraudFactorInputs(
        ocr_accuracy=0.95,
        tampering_score=8.0,
        image_quality_score=90.0,
        is_duplicate=True,
        duplicate_detail={
            "same_owner": True,
            "duplicate_type": "EXACT_FILE_DUPLICATE",
            "owner_distinction": "SAME_OWNER_REUPLOAD"
        }
    )
    result = compute_fraud_analysis(inputs)

    # Benign re-upload should NOT trigger duplicate floor
    assert not any("duplicate_floor" in ov for ov in result.critical_overrides_applied)
    assert result.fraud_probability < 0.25
    assert result.risk_level == "LOW"


def test_per_signal_contribution_breakdown():
    inputs = FraudFactorInputs(
        ocr_accuracy=0.90,
        tampering_score=60.0,
        image_quality_score=80.0,
        metadata_flags=["Software: Adobe Photoshop"],
    )
    result = compute_fraud_analysis(inputs)

    # Check contributions structure
    assert len(result.signal_contributions) == 8
    active_contribs = [sc for sc in result.signal_contributions if sc.is_active]
    assert len(active_contribs) == 4

    # Sum of active contributions must match base probability
    sum_contrib = sum(sc.contribution for sc in active_contribs)
    assert abs(sum_contrib - result.base_probability) < 1e-3

    # Check that Photoshop metadata has CRITICAL or WARNING status
    meta_contrib = next(sc for sc in result.signal_contributions if sc.signal == "metadata_integrity")
    assert meta_contrib.status in ("WARNING", "CRITICAL")
    assert "Adobe Photoshop" in meta_contrib.details or "editing" in meta_contrib.details.lower()
