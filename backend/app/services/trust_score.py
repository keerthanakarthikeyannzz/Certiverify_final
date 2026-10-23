"""
MODULE 6 — TRUST SCORE ENGINE (trust_score)

Computes an explainable, monotonic 0-100 Trust Score from positive evidence
(verified QR, blockchain match, consistent OCR, clean tampering, unique document)
and AI fraud analysis.

Mathematical Monotonicity:
    Let S_A be the trust score computed over evaluated evidence set A:
        S_A = (sum_{i in A} w_i * V_i) / (sum_{i in A} w_i)
    When a new piece of verified evidence k is added with V_k = 100:
        S_{A + {k}} = (sum_{i in A} w_i * V_i + w_k * 100) / (sum_{i in A} w_i + w_k)
    Since V_i <= 100 for all i, S_A <= 100.
    Thus, S_{A + {k}} >= S_A.
    Proof: S_{A + {k}} - S_A = [w_k * (100 - S_A)] / (W_A + w_k) >= 0.
    Therefore, adding more verified positive evidence NEVER lowers the trust score.

Unavailable / Not Evaluated Signals:
    Components that are unconfigured or not applicable (e.g. no QR on document,
    or blockchain not configured) are explicitly listed as "not evaluated" with
    effective weight 0.0 and contribution 0.0. They are EXCLUDED from the weighting
    and are NOT treated as zero.

Coverage Metric:
    coverage = (evaluated_checks) / (total_checks=8).
    This allows the UI and downstream systems to distinguish between a 95/100
    score based on 2 of 8 checks (25% coverage) versus 8 of 8 checks (100% coverage).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional

from app.core.config import settings


@dataclass
class TrustScoreInputs:
    # ── 1. OCR Accuracy & Field Extraction ──
    ocr_accuracy: float | None = None                   # 0-1 or 0-100
    field_confidences: dict[str, float] | None = None
    field_extraction_completeness: float | None = None  # 0-1
    doc_classification_confidence: float | None = None  # 0-1

    # ── 2. Cross-document comparison ──
    document_consistency_pct: float | None = None       # 0-100

    # ── 3. QR verification ──
    qr_present: bool | None = None
    qr_valid: bool | None = None
    qr_warning: str | None = None

    # ── 4. Blockchain verification ──
    blockchain_status: str | None = None                # verified | not_found | mismatch | unavailable
    blockchain_match: bool | None = None

    # ── 5. Tampering analysis ──
    tampering_score: float | None = None                # 0-100, higher = worse
    tampering_status: str | None = None
    tampering_risk_level: str | None = None

    # ── 6. Duplicate detection ──
    is_duplicate: bool | None = None
    duplicate_status: str | None = None
    duplicate_same_owner: bool | None = None
    duplicate_type: str | None = None
    duplicate_detail: dict[str, Any] | None = None

    # ── 7. AI Fraud probability ──
    fraud_probability: float | None = None              # 0-1, higher = worse

    # ── 8. Image quality ──
    image_quality_score: float | None = None            # 0-100, higher = better
    image_quality_details: dict[str, Any] | None = None


@dataclass
class ComponentBreakdown:
    component: str
    label: str
    value: float | None                                 # 0-100 or None if not evaluated
    weight: float                                       # effective weight (0-1)
    contribution: float                                 # value * weight
    status: str                                         # PASS | WARN | FAIL | not evaluated
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "component": self.component,
            "label": self.label,
            "value": round(self.value, 1) if self.value is not None else None,
            "weight": round(self.weight, 4),
            "contribution": round(self.contribution, 2),
            "status": self.status,
            "reason": self.reason,
        }


@dataclass
class TrustScoreResult:
    score: float                                         # 0-100
    band: str                                            # HIGH | MEDIUM | LOW
    band_label: str                                      # High Trust | Medium Trust | Low Trust
    coverage: float                                      # 0.0 - 1.0 (e.g. 0.75)
    coverage_percentage: float                           # 0.0 - 100.0 (e.g. 75.0)
    checks_evaluated: int                                # e.g. 6
    checks_total: int                                    # 8
    components: list[ComponentBreakdown] = field(default_factory=list)
    breakdown: dict[str, Any] = field(default_factory=dict)
    factor_trust_values: dict[str, float] = field(default_factory=dict)
    hard_ceilings_applied: list[str] = field(default_factory=list)

    # Legacy compatibility fields
    evidence_breakdown: dict[str, Any] = field(default_factory=dict)
    checks_completed: int = 0
    partial_verification_note: str = ""


TRUST_COMPONENT_KEYS = [
    "qr",
    "blockchain",
    "ocr",
    "tampering",
    "duplicate",
    "fraud_analysis",
    "comparison",
    "image_quality",
]

TRUST_COMPONENT_LABELS: dict[str, str] = {
    "qr": "QR Code Cryptographic Verification",
    "blockchain": "Blockchain Ledger Proof",
    "ocr": "OCR Accuracy & Field Completeness",
    "tampering": "Tampering & ELA Cleanliness",
    "duplicate": "Document Uniqueness & Collision Registry",
    "fraud_analysis": "AI Fraud Analysis Assessment",
    "comparison": "Cross-Document Comparison Consistency",
    "image_quality": "Scan Resolution & Image Fidelity",
}


def get_nominal_trust_weights() -> dict[str, float]:
    """Load default nominal trust weights from settings or fallback."""
    weights = {
        "qr": getattr(settings, "TRUST_WEIGHT_QR", 0.15),
        "blockchain": getattr(settings, "TRUST_WEIGHT_BLOCKCHAIN", 0.15),
        "ocr": getattr(settings, "TRUST_WEIGHT_OCR", 0.15),
        "tampering": getattr(settings, "TRUST_WEIGHT_TAMPERING", 0.15),
        "duplicate": getattr(settings, "TRUST_WEIGHT_DUPLICATE", 0.10),
        "fraud_analysis": getattr(settings, "TRUST_WEIGHT_FRAUD", 0.10),
        "comparison": getattr(settings, "TRUST_WEIGHT_COMPARISON", 0.10),
        "image_quality": getattr(settings, "TRUST_WEIGHT_IMAGE_QUALITY", 0.10),
    }
    total = sum(weights.values())
    if total <= 0:
        return {k: 1.0 / len(weights) for k in weights}
    return weights


def compute_trust_score(inputs: TrustScoreInputs) -> TrustScoreResult:
    """
    Computes a 0-100 Trust Score from positive evidence and fraud analysis.

    Requirements:
    1. Monotonic: more verified evidence never lowers the score.
    2. Components that are unavailable are listed as "not evaluated" with
       weight 0.0 and contribution 0.0; not treated as zero.
    3. Computes coverage (evaluated / total).
    4. Categorizes into score bands from settings (HIGH/MEDIUM/LOW).
    """
    nominal_weights = get_nominal_trust_weights()

    raw_values: dict[str, float | None] = {}
    statuses: dict[str, str] = {}
    reasons: dict[str, str] = {}

    # ── 1. QR Verification ──
    if inputs.qr_present is None or inputs.qr_present is False:
        raw_values["qr"] = None
        statuses["qr"] = "not evaluated"
        reasons["qr"] = "No QR code detected on document (stage not evaluated)."
    elif inputs.qr_valid is True:
        raw_values["qr"] = 100.0
        statuses["qr"] = "PASS"
        reasons["qr"] = "QR payload cryptographically authenticated with institutional issuer."
    elif inputs.qr_valid is False:
        raw_values["qr"] = 0.0
        statuses["qr"] = "FAIL"
        reasons["qr"] = f"QR payload invalid or tampered: {inputs.qr_warning or 'verification failed'}."
    else:
        raw_values["qr"] = 50.0
        statuses["qr"] = "WARN"
        reasons["qr"] = f"QR present with warning or unverified domain: {inputs.qr_warning or 'untrusted domain'}."

    # ── 2. Blockchain Ledger Proof ──
    bc_st = (inputs.blockchain_status or "").lower()
    if bc_st in ("", "unavailable", "not_applicable", "skipped", "none"):
        raw_values["blockchain"] = None
        statuses["blockchain"] = "not evaluated"
        reasons["blockchain"] = "Blockchain verification not configured or unavailable."
    elif bc_st == "verified" or inputs.blockchain_match is True:
        raw_values["blockchain"] = 100.0
        statuses["blockchain"] = "PASS"
        reasons["blockchain"] = "Cryptographic hash verified and anchored on immutable blockchain ledger."
    elif bc_st == "mismatch" or inputs.blockchain_match is False:
        raw_values["blockchain"] = 0.0
        statuses["blockchain"] = "FAIL"
        reasons["blockchain"] = "Cryptographic hash mismatch against immutable blockchain record."
    elif bc_st == "not_found":
        raw_values["blockchain"] = 50.0
        statuses["blockchain"] = "WARN"
        reasons["blockchain"] = "Document hash not registered on blockchain (unanchored credential)."
    else:
        raw_values["blockchain"] = 50.0
        statuses["blockchain"] = "WARN"
        reasons["blockchain"] = f"Blockchain verification returned status '{inputs.blockchain_status}'."

    # ── 3. OCR Accuracy & Field Completeness ──
    if inputs.ocr_accuracy is None:
        raw_values["ocr"] = None
        statuses["ocr"] = "not evaluated"
        reasons["ocr"] = "OCR text extraction not performed."
    else:
        acc = float(inputs.ocr_accuracy)
        if acc > 1.0:
            acc /= 100.0
        acc = min(max(acc, 0.0), 1.0)

        # Blend with extraction completeness if available
        comp = inputs.field_extraction_completeness
        if comp is not None:
            c_val = min(max(float(comp), 0.0), 1.0)
            effective_ocr = 0.70 * acc + 0.30 * c_val
        else:
            effective_ocr = acc

        val = round(effective_ocr * 100.0, 1)
        raw_values["ocr"] = val
        if val >= 80.0:
            statuses["ocr"] = "PASS"
        elif val >= 50.0:
            statuses["ocr"] = "WARN"
        else:
            statuses["ocr"] = "FAIL"

        comp_str = f" with {round(comp * 100)}% fields extracted" if comp is not None else ""
        reasons["ocr"] = f"OCR overall accuracy: {round(acc * 100, 1)}%{comp_str}."

    # ── 4. Tampering & ELA Cleanliness ──
    t_stat = (inputs.tampering_status or "").lower()
    if inputs.tampering_score is None or t_stat == "not_applicable_for_pdf_text_layer":
        raw_values["tampering"] = None
        statuses["tampering"] = "not evaluated"
        reasons["tampering"] = "Tampering detection not evaluated or not applicable."
    else:
        t_score = float(inputs.tampering_score)
        val = round(max(0.0, min(100.0 - t_score, 100.0)), 1)
        raw_values["tampering"] = val
        if t_score < 25.0:
            statuses["tampering"] = "PASS"
            reasons["tampering"] = f"Authentic visual analysis: tampering score {round(t_score, 1)}/100 [LOW]."
        elif t_score < 60.0:
            statuses["tampering"] = "WARN"
            reasons["tampering"] = f"Minor visual anomalies detected: tampering score {round(t_score, 1)}/100 [MODERATE]."
        else:
            statuses["tampering"] = "FAIL"
            reasons["tampering"] = f"Significant tampering detected: tampering score {round(t_score, 1)}/100 [HIGH RISK]."

    # ── 5. Duplicate Detection & Uniqueness ──
    if inputs.is_duplicate is None:
        raw_values["duplicate"] = None
        statuses["duplicate"] = "not evaluated"
        reasons["duplicate"] = "Duplicate detection not evaluated."
    elif not inputs.is_duplicate:
        raw_values["duplicate"] = 100.0
        statuses["duplicate"] = "PASS"
        reasons["duplicate"] = "Unique credential: no matching duplicate records found in registry."
    else:
        detail = inputs.duplicate_detail or {}
        same_owner = bool(
            inputs.duplicate_same_owner
            or detail.get("same_owner")
            or detail.get("owner_distinction") == "SAME_OWNER_REUPLOAD"
            or (inputs.duplicate_status or "").lower() == "own_reupload"
        )
        is_altered = (
            "altered" in (inputs.duplicate_status or "").lower()
            or (inputs.duplicate_type or "").upper() == "ALTERED_REUPLOAD"
        )
        dup_type = (inputs.duplicate_type or detail.get("duplicate_type") or "").upper()

        if same_owner and not is_altered:
            raw_values["duplicate"] = 100.0
            statuses["duplicate"] = "PASS"
            reasons["duplicate"] = "Benign re-upload: certificate re-submitted by the verified original owner."
        elif is_altered:
            raw_values["duplicate"] = 50.0
            statuses["duplicate"] = "WARN"
            reasons["duplicate"] = "Altered re-upload: matching registration number with conflicting file content."
        elif dup_type in ("CERTIFICATE_CONFLICT", "IDENTITY_CONFLICT"):
            raw_values["duplicate"] = 0.0
            statuses["duplicate"] = "FAIL"
            reasons["duplicate"] = "Identity conflict: certificate number registered to another student identity."
        else:
            raw_values["duplicate"] = 0.0
            statuses["duplicate"] = "FAIL"
            reasons["duplicate"] = "Duplicate collision: identical certificate previously registered by another account."

    # ── 6. AI Fraud Analysis Assessment ──
    if inputs.fraud_probability is None:
        raw_values["fraud_analysis"] = None
        statuses["fraud_analysis"] = "not evaluated"
        reasons["fraud_analysis"] = "AI fraud analysis not yet performed."
    else:
        fp = min(max(float(inputs.fraud_probability), 0.0), 1.0)
        val = round((1.0 - fp) * 100.0, 1)
        raw_values["fraud_analysis"] = val
        if fp < 0.25:
            statuses["fraud_analysis"] = "PASS"
            reasons["fraud_analysis"] = f"AI fraud assessment: clean risk profile ({round(fp * 100, 1)}% fraud probability)."
        elif fp < 0.50:
            statuses["fraud_analysis"] = "WARN"
            reasons["fraud_analysis"] = f"AI fraud assessment: moderate risk detected ({round(fp * 100, 1)}% fraud probability)."
        else:
            statuses["fraud_analysis"] = "FAIL"
            reasons["fraud_analysis"] = f"AI fraud assessment: high fraud risk ({round(fp * 100, 1)}% fraud probability)."

    # ── 7. Cross-Document Comparison ──
    if inputs.document_consistency_pct is None:
        raw_values["comparison"] = None
        statuses["comparison"] = "not evaluated"
        reasons["comparison"] = "Single document upload: cross-document comparison not applicable."
    else:
        c_pct = min(max(float(inputs.document_consistency_pct), 0.0), 100.0)
        val = round(c_pct, 1)
        raw_values["comparison"] = val
        if val >= 80.0:
            statuses["comparison"] = "PASS"
        elif val >= 50.0:
            statuses["comparison"] = "WARN"
        else:
            statuses["comparison"] = "FAIL"
        reasons["comparison"] = f"Cross-document consistency: {val}% across sibling cohort records."

    # ── 8. Image Quality & Scan Fidelity ──
    if inputs.image_quality_score is None:
        raw_values["image_quality"] = None
        statuses["image_quality"] = "not evaluated"
        reasons["image_quality"] = "Scan image quality analysis not available."
    else:
        iq = min(max(float(inputs.image_quality_score), 0.0), 100.0)
        val = round(iq, 1)
        raw_values["image_quality"] = val
        if val >= 75.0:
            statuses["image_quality"] = "PASS"
            reasons["image_quality"] = f"Scan fidelity: crisp resolution and high contrast ({val}/100)."
        elif val >= 50.0:
            statuses["image_quality"] = "WARN"
            reasons["image_quality"] = f"Scan fidelity: acceptable resolution ({val}/100)."
        else:
            statuses["image_quality"] = "FAIL"
            reasons["image_quality"] = f"Scan fidelity: blurry, low resolution, or low contrast ({val}/100)."

    # ── Coverage & Weight Renormalization ──
    active_keys = [k for k in TRUST_COMPONENT_KEYS if raw_values[k] is not None]
    checks_evaluated = len(active_keys)
    checks_total = len(TRUST_COMPONENT_KEYS)
    coverage = round(checks_evaluated / checks_total, 4)
    coverage_percentage = round(coverage * 100.0, 1)

    total_active_nominal = sum(nominal_weights[k] for k in active_keys)
    effective_weights: dict[str, float] = {}
    components: list[ComponentBreakdown] = []
    factor_trust_values: dict[str, float] = {}
    evidence_breakdown: dict[str, Any] = {}

    if total_active_nominal > 0:
        for k in TRUST_COMPONENT_KEYS:
            nom_w = nominal_weights[k]
            val = raw_values[k]
            st = statuses[k]
            rs = reasons[k]

            if val is not None:
                eff_w = round(nom_w / total_active_nominal, 4)
                contrib = round(eff_w * val, 2)
                factor_trust_values[k] = val
                evidence_breakdown[k] = {"score": val, "status": st, "display_status": st, "label": rs}
            else:
                eff_w = 0.0
                contrib = 0.0
                t_st = (inputs.tampering_status or "").lower() if k == "tampering" else ""
                disp_st = "FAILED" if "failed" in t_st else "UNAVAILABLE"
                evidence_breakdown[k] = {"score": None, "status": "UNAVAILABLE", "display_status": disp_st, "label": rs}

            effective_weights[k] = eff_w
            components.append(
                ComponentBreakdown(
                    component=k,
                    label=TRUST_COMPONENT_LABELS.get(k, k),
                    value=val,
                    weight=eff_w,
                    contribution=contrib,
                    status=st,
                    reason=rs,
                )
            )

        base_score = sum(effective_weights[k] * raw_values[k] for k in active_keys)
        base_score = round(min(max(base_score, 0.0), 100.0), 2)
    else:
        # Neutral default if no checks were run at all
        base_score = 50.0
        for k in TRUST_COMPONENT_KEYS:
            effective_weights[k] = 0.0
            components.append(
                ComponentBreakdown(
                    component=k,
                    label=TRUST_COMPONENT_LABELS.get(k, k),
                    value=None,
                    weight=0.0,
                    contribution=0.0,
                    status="not evaluated",
                    reason="Not evaluated: stage not executed",
                )
            )

    # ── Hard Ceilings for Critical Fraud Evidence ──
    final_score = base_score
    ceilings_applied: list[str] = []

    # 1. Blockchain Mismatch Ceiling
    if inputs.blockchain_status == "mismatch" or inputs.blockchain_match is False:
        if final_score > 49.0:
            final_score = 49.0
            ceilings_applied.append("blockchain_mismatch_ceiling_49")

    # 2. Duplicate Collision Ceiling (different owner / conflict)
    if inputs.is_duplicate:
        dup_detail = inputs.duplicate_detail or {}
        same_owner = bool(
            inputs.duplicate_same_owner
            or dup_detail.get("same_owner")
            or dup_detail.get("owner_distinction") == "SAME_OWNER_REUPLOAD"
            or (inputs.duplicate_status or "").lower() == "own_reupload"
        )
        is_altered = (
            "altered" in (inputs.duplicate_status or "").lower()
            or (inputs.duplicate_type or "").upper() == "ALTERED_REUPLOAD"
        )
        if not same_owner and not is_altered:
            if final_score > 15.0:
                final_score = 15.0
                ceilings_applied.append("different_owner_duplicate_ceiling_15")
        elif is_altered:
            if final_score > 65.0:
                final_score = 65.0
                ceilings_applied.append("altered_reupload_ceiling_65")

    # 3. Invalid QR Ceiling
    if inputs.qr_present is True and inputs.qr_valid is False:
        if final_score > 64.0:
            final_score = 64.0
            ceilings_applied.append("invalid_qr_ceiling_64")

    # 4. Severe Tampering Ceiling
    if inputs.tampering_score is not None and inputs.tampering_score >= 70.0:
        if final_score > 59.0:
            final_score = 59.0
            ceilings_applied.append("severe_tampering_ceiling_59")

    final_score = round(min(max(final_score, 0.0), 100.0), 2)

    # ── Score Band Classification from Settings ──
    band_high = getattr(settings, "TRUST_SCORE_BAND_HIGH", 80.0)
    band_medium = getattr(settings, "TRUST_SCORE_BAND_MEDIUM", 50.0)

    if final_score >= band_high:
        band = "HIGH"
        band_label = "High Trust"
    elif final_score >= band_medium:
        band = "MEDIUM"
        band_label = "Medium Trust"
    else:
        band = "LOW"
        band_label = "Low Trust"

    # Enriched breakdown dict for JSON persistence in trust_scores table
    breakdown_dict = {
        "score": final_score,
        "band": band,
        "band_label": band_label,
        "coverage": {
            "evaluated": checks_evaluated,
            "total": checks_total,
            "ratio": coverage,
            "percentage": coverage_percentage,
            "summary": f"{checks_evaluated} of {checks_total} checks evaluated ({coverage_percentage}% coverage)",
        },
        "components": [c.to_dict() for c in components],
        "hard_ceilings_applied": ceilings_applied,
        # Legacy fields for backward compatibility
        "weights": effective_weights,
        "factor_trust_values": factor_trust_values,
        "evidence_breakdown": evidence_breakdown,
        **{k: (raw_values.get(k) or 0.0) for k in TRUST_COMPONENT_KEYS},
    }

    partial_note = f"Partial verification: {checks_evaluated} of {checks_total} checks completed ({coverage_percentage}% coverage)"

    return TrustScoreResult(
        score=final_score,
        band=band,
        band_label=band_label,
        coverage=coverage,
        coverage_percentage=coverage_percentage,
        checks_evaluated=checks_evaluated,
        checks_total=checks_total,
        components=components,
        breakdown=breakdown_dict,
        factor_trust_values=factor_trust_values,
        hard_ceilings_applied=ceilings_applied,
        evidence_breakdown=evidence_breakdown,
        checks_completed=checks_evaluated,
        partial_verification_note=partial_note,
    )
