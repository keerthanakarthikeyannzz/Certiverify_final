"""
MODULE 5 — AI FRAUD ANALYSIS (fraud_analysis)

Combines normalized risk signals from earlier verification stages:
1. OCR accuracy & field extraction confidences
2. Cross-document comparison (document_comparisons)
3. QR result (presence, validity, host trust)
4. Blockchain status (verified, mismatch, not_found, unavailable)
5. Tampering score & risk level
6. Duplicate detection (owner distinction, collision, conflict)
7. Metadata integrity & suspicious editing software flags
8. Scan image quality (sharpness, resolution, contrast)

Design Principles:
- Every signal is mapped to a 0-1 risk value by an explicit normalizer function.
- Missing signals (e.g. NOT_APPLICABLE, SKIPPED, or unavailable) are EXCLUDED,
  and the remaining weights are renormalised to sum to 1.0. A missing signal
  does NOT count as "safe" or "risky".
- Nominal weights come from application settings / environment variables,
  mapping 1:1 to the 8 columns of the `fraud_analysis` database table.
- Configurable hard-floor overrides enforce minimum fraud probabilities on
  near-conclusive fraud signals (e.g. blockchain mismatch, stolen register number).
- Detailed per-signal contributions (risk, weight, contribution, status, details)
  are returned for complete UI explainability.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional

from app.core.config import settings


@dataclass
class FraudFactorInputs:
    # ── 1. OCR Accuracy & Field Confidences ──
    ocr_accuracy: float | None = None                   # 0-1 or 0-100
    field_confidences: dict[str, float] | None = None   # field -> 0-1 or 0-100

    # ── 2. Cross-document comparison ──
    comparison_consistency_pct: float | None = None     # 0-100

    # ── 3. QR verification ──
    qr_present: bool | None = None
    qr_valid: bool | None = None
    qr_warning: str | None = None

    # ── 4. Blockchain verification ──
    blockchain_status: str | None = None                # verified | not_found | mismatch | unavailable
    blockchain_match: bool | None = None

    # ── 5. Tampering analysis ──
    tampering_score: float | None = None                # 0-100, higher = more tampering
    tampering_risk_level: str | None = None             # LOW | MINOR_ANOMALIES | MODERATE_RISK | HIGH_RISK | VERY_HIGH_RISK

    # ── 6. Duplicate detection ──
    is_duplicate: bool | None = None
    duplicate_detail: dict[str, Any] | None = None
    duplicate_type: str | None = None
    duplicate_status: str | None = None
    duplicate_same_owner: bool | None = None

    # ── 7. Metadata integrity ──
    metadata_flags: list[str] | None = None
    metadata_flags_present: bool | None = None

    # ── 8. Image quality ──
    image_quality_score: float | None = None            # 0-100, higher = better quality
    image_quality_details: dict[str, Any] | None = None

    # Additional contextual indicators
    doc_classification_confidence: float | None = None
    field_extraction_completeness: float | None = None
    text_consistency_score: float | None = None
    signature_present: bool | None = None
    seal_present: bool | None = None


@dataclass
class SignalContributionDetail:
    signal: str
    label: str
    is_active: bool
    nominal_weight: float
    effective_weight: float
    risk: float | None
    contribution: float
    status: str                                         # CLEAN | WARNING | CRITICAL | NOT_APPLICABLE
    details: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal": self.signal,
            "label": self.label,
            "is_active": self.is_active,
            "nominal_weight": round(self.nominal_weight, 4),
            "effective_weight": round(self.effective_weight, 4),
            "risk": round(self.risk, 4) if self.risk is not None else None,
            "contribution": round(self.contribution, 4),
            "status": self.status,
            "details": self.details,
        }


@dataclass
class FraudAnalysisResult:
    fraud_probability: float                            # 0-1 (post-override)
    base_probability: float                             # 0-1 (pre-override weighted sum)
    risk_level: str                                     # LOW | MODERATE | HIGH | VERY_HIGH
    factor_weights: dict[str, float] = field(default_factory=dict)  # effective weights (8 factors)
    factor_risks: dict[str, float] = field(default_factory=dict)    # normalized 0-1 risks
    signal_contributions: list[SignalContributionDetail] = field(default_factory=list)
    critical_overrides_applied: list[str] = field(default_factory=list)
    image_quality_details: dict[str, Any] | None = None


SIGNAL_KEYS = [
    "ocr_accuracy",
    "comparison",
    "qr",
    "blockchain",
    "tampering",
    "duplicate",
    "metadata_integrity",
    "image_quality",
]

SIGNAL_LABELS: dict[str, str] = {
    "ocr_accuracy": "OCR Extraction & Field Confidences",
    "comparison": "Cross-Document Comparison Consistency",
    "qr": "QR Code Verification & Payload Validation",
    "blockchain": "Blockchain Cryptographic Proof",
    "tampering": "Tampering & Forgery Detection (ELA/Metadata)",
    "duplicate": "Duplicate & Credential Collision Detection",
    "metadata_integrity": "Metadata & Software Provenance Integrity",
    "image_quality": "Scan Quality (Sharpness/Resolution/Contrast)",
}


def get_nominal_weights() -> dict[str, float]:
    """Load default nominal weights from app settings."""
    weights = {
        "ocr_accuracy": getattr(settings, "FRAUD_WEIGHT_OCR_ACCURACY", 0.15),
        "comparison": getattr(settings, "FRAUD_WEIGHT_COMPARISON", 0.15),
        "qr": getattr(settings, "FRAUD_WEIGHT_QR", 0.10),
        "blockchain": getattr(settings, "FRAUD_WEIGHT_BLOCKCHAIN", 0.15),
        "tampering": getattr(settings, "FRAUD_WEIGHT_TAMPERING", 0.20),
        "duplicate": getattr(settings, "FRAUD_WEIGHT_DUPLICATE", 0.10),
        "metadata_integrity": getattr(settings, "FRAUD_WEIGHT_METADATA_INTEGRITY", 0.05),
        "image_quality": getattr(settings, "FRAUD_WEIGHT_IMAGE_QUALITY", 0.10),
    }
    total = sum(weights.values())
    if total <= 0:
        return {k: 1.0 / len(weights) for k in weights}
    return weights


# =============================================================================
# NORMALIZER FUNCTIONS (Signal -> 0-1 Risk)
# =============================================================================

def normalize_ocr_accuracy(
    ocr_acc: float | None,
    field_confidences: dict[str, float] | None,
) -> tuple[float | None, str]:
    """
    Normalizes OCR accuracy and average field extraction confidence into a 0-1 risk.
    High accuracy (95%+) -> low risk (~0.05). Low accuracy (30%) -> high risk (~0.70).
    """
    if ocr_acc is None:
        return None, "OCR extraction data not available (omitted from risk scoring)"

    acc_val = float(ocr_acc)
    if acc_val > 1.0:
        acc_val /= 100.0
    acc_val = min(max(acc_val, 0.0), 1.0)

    # Blend with field-level extraction confidences if available
    if field_confidences and isinstance(field_confidences, dict) and len(field_confidences) > 0:
        confs = []
        for val in field_confidences.values():
            if isinstance(val, (int, float)):
                v = float(val)
                if v > 1.0:
                    v /= 100.0
                confs.append(min(max(v, 0.0), 1.0))
        if confs:
            avg_field_conf = sum(confs) / len(confs)
            effective_acc = 0.70 * acc_val + 0.30 * avg_field_conf
        else:
            effective_acc = acc_val
    else:
        effective_acc = acc_val

    risk = round(1.0 - effective_acc, 4)
    details = f"OCR overall accuracy: {round(acc_val * 100, 1)}% (effective score {round(effective_acc * 100, 1)}%)"
    return risk, details


def normalize_comparison(consistency_pct: float | None) -> tuple[float | None, str]:
    """
    Normalizes cross-document comparison consistency percentage (0-100) to 0-1 risk.
    100% consistent -> 0.0 risk. 50% consistent -> 0.5 risk.
    If no comparison was run (single doc upload), returns None (excluded).
    """
    if consistency_pct is None:
        return None, "Cross-document comparison not applicable (single document upload)"

    c_val = float(consistency_pct)
    c_val = min(max(c_val, 0.0), 100.0)
    risk = round(1.0 - (c_val / 100.0), 4)
    details = f"Cross-document consistency: {round(c_val, 1)}% across sibling records"
    return risk, details


def normalize_qr(
    present: bool | None,
    valid: bool | None,
    warning: str | None,
) -> tuple[float | None, str]:
    """
    Normalizes QR code verification status.
    If QR code is not present on the document, stage was NOT_APPLICABLE -> None.
    If QR is valid -> 0.0 risk.
    If QR is invalid / forged -> 0.85 risk.
    If QR has warnings (e.g. untrusted domain) -> 0.40 risk.
    """
    if present is None or present is False:
        # A document without a QR code is excluded so it does not count as safe or risky
        return None, "QR code not present on document (stage not applicable)"

    if valid is True:
        return 0.0, "QR code payload verified and authenticated"
    elif valid is False:
        return 0.85, f"QR code payload invalid or tampered: {warning or 'data mismatch'}"
    else:
        return 0.40, f"QR code present with unverified domain or warning: {warning or 'untrusted domain'}"


def normalize_blockchain(
    status: str | None,
    match: bool | None,
) -> tuple[float | None, str]:
    """
    Normalizes blockchain ledger verification.
    If blockchain not configured or unavailable -> None (excluded).
    If verified / match=True -> 0.0 risk.
    If mismatch / match=False -> 1.0 risk (critical fraud indicator).
    If not_found -> 0.35 risk (unanchored credential).
    """
    if status is None or status.lower() in ("unavailable", "not_applicable", "skipped", "none", ""):
        return None, "Blockchain verification not configured or unavailable (excluded)"

    st = status.lower()
    if st == "verified" or match is True:
        return 0.0, "Cryptographic hash verified on blockchain ledger"
    elif st == "mismatch" or match is False:
        return 1.0, "Critical cryptographic hash mismatch against blockchain record"
    elif st == "not_found":
        return 0.35, "Document hash not registered on blockchain (unanchored)"
    else:
        return 0.35, f"Blockchain verification returned status '{status}'"


def normalize_tampering(
    score: float | None,
    risk_level: str | None,
) -> tuple[float | None, str]:
    """
    Normalizes tampering score (0-100) directly to 0-1 risk.
    """
    if score is None:
        return None, "Tampering detection not yet executed (excluded)"

    s_val = float(score)
    risk = round(min(max(s_val / 100.0, 0.0), 1.0), 4)
    level_str = f" [{risk_level}]" if risk_level else ""
    details = f"Tampering score: {round(s_val, 1)}/100{level_str}"
    return risk, details


def normalize_duplicate(
    is_duplicate: bool | None,
    detail: dict[str, Any] | None,
) -> tuple[float | None, str]:
    """
    Normalizes duplicate detection result, distinguishing same-owner re-upload (benign)
    from credential collision / identity conflict (severe fraud).
    """
    if is_duplicate is None:
        return None, "Duplicate detection not yet executed (excluded)"

    if not is_duplicate:
        return 0.0, "No duplicate records found in registry (clean)"

    detail = detail or {}
    same_owner = bool(
        detail.get("same_owner")
        or detail.get("owner_distinction") == "SAME_OWNER_REUPLOAD"
        or detail.get("duplicate_status") == "own_reupload"
    )
    dup_type = (detail.get("duplicate_type") or "").upper()
    dup_status = (detail.get("duplicate_status") or "").upper()
    owner_dist = (detail.get("owner_distinction") or "").upper()

    if same_owner:
        return 0.0, "Re-upload of identical document by original owner (benign re-submission)"

    if dup_type in ("CERTIFICATE_CONFLICT", "IDENTITY_CONFLICT") or dup_status == "CERTIFICATE_CONFLICT":
        return 1.0, "Identity conflict: same register number issued to a conflicting student name"

    if dup_type == "EXACT_FILE_DUPLICATE" or owner_dist == "DIFFERENT_OWNER_DUPLICATE":
        return 0.90, "Identical certificate file previously uploaded by a different account"

    if dup_type == "PERCEPTUAL_DUPLICATE_DIFFERENT_OWNER":
        return 0.85, "Visually identical certificate previously uploaded by a different account"

    if dup_type == "IDENTITY_DUPLICATE_DIFFERENT_OWNER":
        return 0.90, "Same student registration number and name uploaded by a different user"

    return 0.70, f"Duplicate certificate record detected ({dup_type or 'cross-account match'})"


def normalize_metadata_integrity(
    flags: list[str] | None,
    flags_present: bool | None,
) -> tuple[float | None, str]:
    """
    Normalizes PDF/image metadata checks (suspicious producers, editing tools, revision anomalies).
    """
    if flags is None and flags_present is None:
        return None, "Metadata integrity check not available (excluded)"

    flag_list = flags or []
    if not flag_list and not flags_present:
        return 0.0, "Document metadata is clean; authentic creator/producer signatures"

    # Inspect for suspicious editing tools (Photoshop, Canva, Illustrator, GIMP, etc.)
    editing_tools = ["photoshop", "canva", "illustrator", "gimp", "coreldraw", "inkscape", "paint.net"]
    has_editing_sw = any(
        any(tool in f.lower() for tool in editing_tools)
        for f in flag_list
    )

    if has_editing_sw:
        risk = round(min(0.70 + 0.10 * len(flag_list), 1.0), 4)
        details = f"Suspicious editing software detected in metadata ({len(flag_list)} flags)"
    else:
        risk = round(min(0.35 + 0.10 * len(flag_list), 0.75), 4)
        details = f"Minor metadata anomalies flagged ({len(flag_list)} signals)"

    return risk, details


def normalize_image_quality(
    score: float | None,
    details: dict[str, Any] | None,
) -> tuple[float | None, str]:
    """
    Normalizes image scan quality (sharpness, resolution, contrast).
    High quality scan (90+) -> low risk (~0.10).
    Degraded, blurry, or washed out scan (25) -> high quality risk (~0.75).
    """
    if score is None:
        return None, "Image quality analysis not available (excluded)"

    q_val = float(score)
    q_val = min(max(q_val, 0.0), 100.0)
    risk = round(max(0.0, min(1.0 - (q_val / 100.0), 1.0)), 4)

    parts = [f"Overall scan quality: {round(q_val, 1)}/100"]
    if details:
        if details.get("is_blurry"):
            parts.append("blurry scan")
        if details.get("is_low_res"):
            parts.append("low resolution")
        if details.get("is_low_contrast"):
            parts.append("low contrast")

    return risk, " | ".join(parts)


# =============================================================================
# FRAUD ANALYSIS ENGINE
# =============================================================================

def compute_fraud_analysis(inputs: FraudFactorInputs) -> FraudAnalysisResult:
    """
    Compute fraud probability from gathered verification signals.

    Excludes missing/NOT_APPLICABLE signals and renormalizes active weights.
    Applies configurable hard-floor overrides for near-conclusive fraud signals.
    """
    nominal_weights = get_nominal_weights()

    # Step 1: Normalize all 8 signals
    raw_risks: dict[str, float | None] = {}
    details_map: dict[str, str] = {}

    r_ocr, d_ocr = normalize_ocr_accuracy(inputs.ocr_accuracy, inputs.field_confidences)
    raw_risks["ocr_accuracy"] = r_ocr
    details_map["ocr_accuracy"] = d_ocr

    r_comp, d_comp = normalize_comparison(inputs.comparison_consistency_pct)
    raw_risks["comparison"] = r_comp
    details_map["comparison"] = d_comp

    r_qr, d_qr = normalize_qr(inputs.qr_present, inputs.qr_valid, inputs.qr_warning)
    raw_risks["qr"] = r_qr
    details_map["qr"] = d_qr

    r_bc, d_bc = normalize_blockchain(inputs.blockchain_status, inputs.blockchain_match)
    raw_risks["blockchain"] = r_bc
    details_map["blockchain"] = d_bc

    r_tamp, d_tamp = normalize_tampering(inputs.tampering_score, inputs.tampering_risk_level)
    raw_risks["tampering"] = r_tamp
    details_map["tampering"] = d_tamp

    # Consolidate duplicate inputs
    dup_detail = inputs.duplicate_detail or {}
    if inputs.duplicate_type:
        dup_detail.setdefault("duplicate_type", inputs.duplicate_type)
    if inputs.duplicate_status:
        dup_detail.setdefault("duplicate_status", inputs.duplicate_status)
    if inputs.duplicate_same_owner is not None:
        dup_detail.setdefault("same_owner", inputs.duplicate_same_owner)

    r_dup, d_dup = normalize_duplicate(inputs.is_duplicate, dup_detail)
    raw_risks["duplicate"] = r_dup
    details_map["duplicate"] = d_dup

    r_meta, d_meta = normalize_metadata_integrity(inputs.metadata_flags, inputs.metadata_flags_present)
    raw_risks["metadata_integrity"] = r_meta
    details_map["metadata_integrity"] = d_meta

    r_img, d_img = normalize_image_quality(inputs.image_quality_score, inputs.image_quality_details)
    raw_risks["image_quality"] = r_img
    details_map["image_quality"] = d_img

    # Step 2: Filter active signals and renormalize weights
    active_keys = [k for k in SIGNAL_KEYS if raw_risks[k] is not None]
    total_active_nominal = sum(nominal_weights[k] for k in active_keys)

    effective_weights: dict[str, float] = {}
    signal_contributions: list[SignalContributionDetail] = []
    factor_risks: dict[str, float] = {}

    if total_active_nominal > 0:
        for k in SIGNAL_KEYS:
            nom_w = nominal_weights[k]
            risk_val = raw_risks[k]
            is_act = risk_val is not None

            if is_act:
                eff_w = round(nom_w / total_active_nominal, 4)
                contribution = round(eff_w * risk_val, 4)
                factor_risks[k] = risk_val

                # Assign categorical status
                if risk_val < 0.25:
                    status = "CLEAN"
                elif risk_val < 0.60:
                    status = "WARNING"
                else:
                    status = "CRITICAL"
            else:
                eff_w = 0.0
                contribution = 0.0
                status = "NOT_APPLICABLE"

            effective_weights[k] = eff_w
            signal_contributions.append(
                SignalContributionDetail(
                    signal=k,
                    label=SIGNAL_LABELS.get(k, k),
                    is_active=is_act,
                    nominal_weight=nom_w,
                    effective_weight=eff_w,
                    risk=risk_val,
                    contribution=contribution,
                    status=status,
                    details=details_map.get(k, ""),
                )
            )

        base_probability = sum(effective_weights[k] * raw_risks[k] for k in active_keys)
        base_probability = round(min(max(base_probability, 0.0), 1.0), 4)
    else:
        # Default neutral fallback if no signals exist
        base_probability = 0.50
        for k in SIGNAL_KEYS:
            effective_weights[k] = 0.0
            signal_contributions.append(
                SignalContributionDetail(
                    signal=k,
                    label=SIGNAL_LABELS.get(k, k),
                    is_active=False,
                    nominal_weight=nominal_weights.get(k, 0.0),
                    effective_weight=0.0,
                    risk=None,
                    contribution=0.0,
                    status="NOT_APPLICABLE",
                    details="No verification signal available",
                )
            )

    # Step 3: Apply Configurable Hard-Override Floors
    overrides_applied: list[str] = []
    final_prob = base_probability

    # 1. Blockchain Mismatch Override
    if inputs.blockchain_status == "mismatch" or inputs.blockchain_match is False:
        fl = getattr(settings, "FRAUD_OVERRIDE_BLOCKCHAIN_MISMATCH_FLOOR", 0.85)
        if final_prob < fl:
            final_prob = fl
            overrides_applied.append(f"blockchain_mismatch_floor_{fl}")

    # 2. Duplicate Collision / Conflict Overrides
    if inputs.is_duplicate:
        same_owner = bool(
            dup_detail.get("same_owner")
            or dup_detail.get("owner_distinction") == "SAME_OWNER_REUPLOAD"
            or dup_detail.get("duplicate_status") == "own_reupload"
        )
        dup_type = (dup_detail.get("duplicate_type") or "").upper()
        dup_status = (dup_detail.get("duplicate_status") or "").upper()
        owner_dist = (dup_detail.get("owner_distinction") or "").upper()

        if dup_type in ("CERTIFICATE_CONFLICT", "IDENTITY_CONFLICT") or dup_status == "CERTIFICATE_CONFLICT":
            fl = getattr(settings, "FRAUD_OVERRIDE_CONFLICT_FLOOR", 0.90)
            if final_prob < fl:
                final_prob = fl
                overrides_applied.append(f"certificate_conflict_floor_{fl}")
        elif not same_owner and (
            owner_dist == "DIFFERENT_OWNER_DUPLICATE"
            or dup_type in ("EXACT_FILE_DUPLICATE", "DUPLICATE_CERTIFICATE", "PERCEPTUAL_DUPLICATE_DIFFERENT_OWNER")
        ):
            fl = getattr(settings, "FRAUD_OVERRIDE_DIFFERENT_OWNER_DUPLICATE_FLOOR", 0.85)
            if final_prob < fl:
                final_prob = fl
                overrides_applied.append(f"different_owner_duplicate_floor_{fl}")

    # 3. Severe Tampering Override
    tamp_score = inputs.tampering_score
    if tamp_score is not None:
        t_thresh = getattr(settings, "FRAUD_OVERRIDE_TAMPERING_THRESHOLD", 70.0)
        t_floor = getattr(settings, "FRAUD_OVERRIDE_TAMPERING_FLOOR", 0.75)
        if tamp_score >= t_thresh and final_prob < t_floor:
            final_prob = t_floor
            overrides_applied.append(f"tampering_severe_floor_{t_floor}")

    # 4. Invalid QR Code Override
    if inputs.qr_present is True and inputs.qr_valid is False:
        qr_fl = getattr(settings, "FRAUD_OVERRIDE_QR_INVALID_FLOOR", 0.65)
        if final_prob < qr_fl:
            final_prob = qr_fl
            overrides_applied.append(f"qr_invalid_floor_{qr_fl}")

    final_prob = round(min(max(final_prob, 0.0), 1.0), 4)

    # Step 4: Derive UI Risk Level
    if final_prob >= 0.70:
        risk_level = "VERY_HIGH"
    elif final_prob >= 0.50:
        risk_level = "HIGH"
    elif final_prob >= 0.25:
        risk_level = "MODERATE"
    else:
        risk_level = "LOW"

    return FraudAnalysisResult(
        fraud_probability=final_prob,
        base_probability=base_probability,
        risk_level=risk_level,
        factor_weights=effective_weights,
        factor_risks=factor_risks,
        signal_contributions=signal_contributions,
        critical_overrides_applied=overrides_applied,
        image_quality_details=inputs.image_quality_details,
    )
