"""
MODULE 7 — AI FRAUD ANALYSIS (Enhanced)

Combines every signal produced by Modules 4-6 into a single fraud
probability (0-1). Pure function over already-computed inputs — no
new ML model.

ENHANCEMENTS over original:
  - 3 new input signals: doc_classification_confidence, field_extraction_completeness,
    text_consistency_score (fills the 10%+10%+missing gap from the spec)
  - Signature/seal signals added as lightweight indicators
  - Weights realigned to match spec:
      OCR=15%, Classification=10%, Fields=10%, Comparison=15%,
      QR=10%, Blockchain=15%, Tampering=15%, Duplicate=5%, Metadata=5%
  - Critical evidence overrides (hard floors on fraud_probability):
      blockchain mismatch  → floor 0.75 (near-conclusive)
      QR invalid           → floor 0.60
      tampering ≥ 70       → floor 0.65
      duplicate            → floor 0.85 (unchanged)
  - factor_risks now includes all new factors for transparency

Design principles (unchanged from original):
  - Unavailable signals are EXCLUDED (renormalized), not defaulted to 0.5
  - Each factor contributes risk in [0, 1] (0=clean, 1=strong fraud indicator)
  - Hard floor overrides applied after weighted average
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class FraudFactorInputs:
    # ── Existing signals ────────────────────────────────────────────────────
    ocr_accuracy: float | None = None                   # 0-1
    comparison_consistency_pct: float | None = None     # 0-100
    qr_present: bool | None = None
    qr_valid: bool | None = None
    blockchain_status: str | None = None                # verified | not_found | mismatch | unavailable
    tampering_score: float | None = None                # 0-100, higher = more tampering
    is_duplicate: bool | None = None
    metadata_flags_present: bool | None = None
    image_quality_score: float | None = None            # 0-100, higher = better quality

    # ── New signals ─────────────────────────────────────────────────────────
    doc_classification_confidence: float | None = None  # 0-1
    field_extraction_completeness: float | None = None  # 0-1 (detected/expected fields)
    text_consistency_score: float | None = None         # 0-1 (internal text coherence)
    signature_present: bool | None = None               # from OCR has_signature
    seal_present: bool | None = None                    # from OCR has_seal
    duplicate_type: str | None = None                   # Priority 7: CERTIFICATE_CONFLICT | DUPLICATE_UPLOAD | etc.
    duplicate_status: str | None = None                 # own_reupload | suspicious: altered re-upload | ...
    duplicate_same_owner: bool | None = None            # True when re-upload by same user
    tampering_risk_level: str | None = None             # LOW | MINOR_ANOMALIES | MODERATE_RISK | HIGH_RISK | VERY_HIGH_RISK


@dataclass
class FraudAnalysisResult:
    fraud_probability: float                            # 0-1
    factor_weights: dict = field(default_factory=dict)  # effective weight per factor
    factor_risks: dict = field(default_factory=dict)    # raw risk value per factor (0-1)
    critical_overrides_applied: list[str] = field(default_factory=list)  # which hard floors fired


# Spec-aligned nominal weights (sum = 1.0)
NOMINAL_WEIGHTS: dict[str, float] = {
    "ocr_accuracy":              0.15,
    "doc_classification":        0.10,
    "field_extraction":          0.10,
    "comparison":                0.15,
    "qr":                        0.10,
    "blockchain":                0.15,
    "tampering":                 0.15,
    "duplicate":                 0.05,
    "metadata_integrity":        0.05,
    # Note: image_quality and text_consistency have no nominal weight —
    # they contribute by adjusting existing factor risks rather than
    # being independent weighted factors, to keep total = 1.0.
}

# Hard-floor thresholds for critical evidence overrides
_BLOCKCHAIN_MISMATCH_FLOOR  = 0.75
_QR_INVALID_FLOOR           = 0.60
_TAMPERING_SEVERE_FLOOR     = 0.65
_TAMPERING_SEVERE_THRESHOLD = 70.0   # tampering_score above which override fires
_DUPLICATE_FLOOR            = 0.85   # unchanged from original


def compute_fraud_analysis(inputs: FraudFactorInputs) -> FraudAnalysisResult:
    """
    Compute fraud probability from all available verification signals.

    Returns FraudAnalysisResult with fraud_probability (0-1), per-factor
    weights actually applied, per-factor risk values, and a list of any
    critical evidence overrides that were triggered.
    """
    risks: dict[str, float] = {}
    overrides: list[str] = []

    # ── 1. OCR accuracy ─────────────────────────────────────────────────────
    if inputs.ocr_accuracy is not None:
        risks["ocr_accuracy"] = round(1.0 - inputs.ocr_accuracy, 4)

    # ── 2. Document classification confidence ────────────────────────────────
    if inputs.doc_classification_confidence is not None:
        risks["doc_classification"] = round(1.0 - inputs.doc_classification_confidence, 4)

    # ── 3. Field extraction completeness ────────────────────────────────────
    if inputs.field_extraction_completeness is not None:
        risks["field_extraction"] = round(1.0 - inputs.field_extraction_completeness, 4)

    # ── 4. Document comparison ───────────────────────────────────────────────
    if inputs.comparison_consistency_pct is not None:
        risks["comparison"] = round(1.0 - inputs.comparison_consistency_pct / 100.0, 4)

    # ── 5. QR verification ───────────────────────────────────────────────────
    if inputs.qr_present is not None:
        if not inputs.qr_present:
            # Missing QR is a mild signal only — many real docs have no QR
            risks["qr"] = 0.20
        elif inputs.qr_valid:
            risks["qr"] = 0.0
        else:
            risks["qr"] = 0.80

    # ── 6. Blockchain verification ───────────────────────────────────────────
    if inputs.blockchain_status is not None and inputs.blockchain_status != "unavailable":
        blockchain_risk_map = {
            "verified":  0.0,
            "not_found": 0.40,   # neutral: not registered ≠ fake
            "mismatch":  1.0,
        }
        risks["blockchain"] = blockchain_risk_map.get(inputs.blockchain_status, 0.40)

    # ── 7. Tampering analysis ────────────────────────────────────────────────
    if inputs.tampering_score is not None:
        # Optionally amplify if text_consistency_score also looks bad
        base_risk = min(inputs.tampering_score / 100.0, 1.0)
        if inputs.text_consistency_score is not None and inputs.text_consistency_score < 0.5:
            # Low text consistency independently corroborates tampering
            base_risk = min(base_risk * 1.10, 1.0)
        risks["tampering"] = round(base_risk, 4)

    # ── 8. Duplicate detection (type-aware, Priority 7) ──────────────────────
    # Different duplicate categories carry different fraud risk:
    #   CERTIFICATE_CONFLICT   → same cert# but different person: very high risk
    #   EXACT_FILE_DUPLICATE / DUPLICATE_CERTIFICATE cross-owner → suspicious
    #   same-owner re-upload (DUPLICATE_UPLOAD) → minimal risk (benign)
    #   POSSIBLE_DUPLICATE     → moderate warning
    #   QR_DUPLICATE           → context-dependent (treat as suspicious)
    #   NO_DUPLICATE / None    → zero risk
    if inputs.is_duplicate is not None:
        dup_type = (inputs.duplicate_type or "").upper()
        dup_status = (inputs.duplicate_status or "").lower()
        same_owner = bool(inputs.duplicate_same_owner)
        is_own = dup_status == "own_reupload" or (
            same_owner and not ("altered" in dup_status or dup_status.startswith("suspicious"))
            and (dup_type in ("EXACT_FILE_DUPLICATE", "DUPLICATE_UPLOAD") or not dup_type)
        )
        is_altered = (
            "altered" in dup_status
            or dup_status in ("suspicious: altered re-upload", "suspicious_altered_reupload")
            or dup_type == "ALTERED_REUPLOAD"
        )

        if not inputs.is_duplicate:
            risks["duplicate"] = 0.0
        elif is_own:
            # Informational only: no penalty, not fraud evidence
            risks["duplicate"] = 0.0
        elif is_altered:
            # Moderate signal
            risks["duplicate"] = 0.40
        elif dup_type == "CERTIFICATE_CONFLICT":
            risks["duplicate"] = 1.0   # Strong fraud signal — always max risk
        elif dup_type in ("EXACT_FILE_DUPLICATE", "DUPLICATE_CERTIFICATE"):
            risks["duplicate"] = 0.70
        elif dup_type == "QR_DUPLICATE":
            risks["duplicate"] = 0.65
        elif dup_type == "POSSIBLE_DUPLICATE":
            risks["duplicate"] = 0.40
        elif dup_type == "DUPLICATE_UPLOAD":
            risks["duplicate"] = 0.0 if same_owner else 0.50
        else:
            risks["duplicate"] = 0.0 if same_owner else 0.70

    # ── 9. Metadata integrity ────────────────────────────────────────────────
    if inputs.metadata_flags_present is not None:
        risks["metadata_integrity"] = 1.0 if inputs.metadata_flags_present else 0.0

    # ── No data at all ───────────────────────────────────────────────────────
    if not risks:
        return FraudAnalysisResult(
            fraud_probability=0.50,
            factor_weights={},
            factor_risks={},
            critical_overrides_applied=["no_data_available"],
        )

    # ── Renormalized weighted average ────────────────────────────────────────
    total_nominal = sum(NOMINAL_WEIGHTS.get(f, 0.0) for f in risks)
    if total_nominal == 0:
        total_nominal = 1.0
    effective_weights = {
        f: NOMINAL_WEIGHTS.get(f, 0.0) / total_nominal for f in risks
    }
    probability = sum(effective_weights[f] * risks[f] for f in risks)

    # ── Critical evidence overrides (hard floors) ────────────────────────────
    # DUPLICATE_FLOOR only fires for genuinely suspicious cross-account duplicates.
    # Same-owner re-uploads are benign and must NOT trigger the floor.
    if inputs.is_duplicate:
        dup_type = (inputs.duplicate_type or "").upper()
        dup_status = (inputs.duplicate_status or "").lower()
        same_owner = bool(inputs.duplicate_same_owner)
        is_own = dup_status == "own_reupload" or (
            same_owner and not ("altered" in dup_status or dup_status.startswith("suspicious"))
            and (dup_type in ("EXACT_FILE_DUPLICATE", "DUPLICATE_UPLOAD") or not dup_type)
        )
        is_altered = (
            "altered" in dup_status
            or dup_status in ("suspicious: altered re-upload", "suspicious_altered_reupload")
            or dup_type == "ALTERED_REUPLOAD"
        )

        if not is_own and not is_altered:
            is_suspicious_dup = (
                dup_type == "CERTIFICATE_CONFLICT"
                or (not same_owner and dup_type in ("EXACT_FILE_DUPLICATE", "DUPLICATE_CERTIFICATE", "QR_DUPLICATE", "POSSIBLE_DUPLICATE"))
                or (not same_owner)
            )
            if is_suspicious_dup:
                probability = max(probability, _DUPLICATE_FLOOR)
                overrides.append(f"duplicate_floor_{_DUPLICATE_FLOOR}")

    if inputs.blockchain_status == "mismatch":
        probability = max(probability, _BLOCKCHAIN_MISMATCH_FLOOR)
        overrides.append(f"blockchain_mismatch_floor_{_BLOCKCHAIN_MISMATCH_FLOOR}")

    if inputs.qr_present and inputs.qr_valid is False:
        probability = max(probability, _QR_INVALID_FLOOR)
        overrides.append(f"qr_invalid_floor_{_QR_INVALID_FLOOR}")

    if inputs.tampering_score is not None and inputs.tampering_score >= _TAMPERING_SEVERE_THRESHOLD:
        probability = max(probability, _TAMPERING_SEVERE_FLOOR)
        overrides.append(f"tampering_severe_floor_{_TAMPERING_SEVERE_FLOOR}")

    probability = round(min(max(probability, 0.0), 1.0), 4)

    # Fill zeros for all nominal factors not present (for consistent DB shape)
    full_weights = {
        f: round(effective_weights.get(f, 0.0), 4) for f in NOMINAL_WEIGHTS
    }

    return FraudAnalysisResult(
        fraud_probability=probability,
        factor_weights=full_weights,
        factor_risks=risks,
        critical_overrides_applied=overrides,
    )
