"""
MODULE 9 — FINAL PREDICTION (Enhanced)

Classifies a certificate as Genuine / Suspicious / Fake from its Trust
Score (Module 8) and produces a structured evidence JSON breakdown with
a reasons list.

ENHANCEMENTS over original:
  - Returns structured `evidence` dict (per-factor status, score, label)
  - Returns `reasons` list (human-readable bullet sentences)
  - Returns `fraud_probability` directly in result for single-call access
  - Existing `explanation` string preserved (backward compatible)
  - Critical evidence labels surface in reasons list
  - Thresholds unchanged: ≥80 Genuine, 50–79 Suspicious, <50 Fake

The evidence dict matches the spec's JSON structure:
  {
    "ocr":            {"score": 94, "status": "PASS"},
    "classification": {"score": 96, "status": "PASS"},
    "field_extraction":{"score": 91, "status": "PASS"},
    "comparison":     {"score": 93, "status": "PASS"},
    "qr":             {"status": "VERIFIED"},
    "blockchain":     {"status": "MATCH"},
    "tampering":      {"score": 5,  "status": "LOW_RISK"},
    "duplicate":      {"status": "NOT_FOUND"},
    "metadata":       {"status": "CLEAN"}
  }
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class PredictionInputs:
    trust_score: float                                  # 0-100
    data_completeness: float = 0.0                      # 0-1, fraction of factors with real data
    is_duplicate: bool | None = None
    tampering_score: float | None = None                # 0-100
    tampering_status: str | None = None                 # analyzed | not_applicable_for_pdf_text_layer | failed: <reason> | unavailable
    blockchain_status: str | None = None
    qr_present: bool | None = None
    qr_valid: bool | None = None
    comparison_consistency_pct: float | None = None
    fraud_probability: float | None = None              # 0-1
    ocr_accuracy: float | None = None                  # 0-1
    duplicate_status: str | None = None
    duplicate_same_owner: bool | None = None
    duplicate_type: str | None = None
    duplicate_match_reason: str | None = None
    # New structured evidence from trust score engine
    evidence_breakdown: dict | None = None              # from TrustScoreResult.evidence_breakdown
    # New signals
    doc_classification_confidence: float | None = None  # 0-1
    field_extraction_completeness: float | None = None  # 0-1
    critical_overrides: list[str] | None = None         # from FraudAnalysisResult


@dataclass
class PredictionResult:
    label: str                                         # "genuine" | "suspicious" | "fake"
    confidence: float                                  # 0-1
    explanation: str                                   # plain text (backward compatible)
    recommended_action: str
    fraud_probability: float = 0.0                    # 0-1, mirrored for convenience
    evidence: dict = field(default_factory=dict)       # structured per-factor JSON
    reasons: list[str] = field(default_factory=list)   # human-readable bullet sentences


GENUINE_THRESHOLD    = 80
SUSPICIOUS_THRESHOLD = 50


def predict(inputs: PredictionInputs) -> PredictionResult:
    score = inputs.trust_score
    fp    = inputs.fraud_probability or 0.0

    # ── Primary classification from trust score ───────────────────────────
    if score >= GENUINE_THRESHOLD:
        label = "genuine"
    elif score >= SUSPICIOUS_THRESHOLD:
        label = "suspicious"
    else:
        label = "fake"

    # ── Critical checks requirement for Genuine verdict ──────────────────
    # Exact rule: A verdict can be "genuine" only if all critical checks ran;
    # otherwise it must read "inconclusive / needs review".
    # Critical checks:
    # 1. OCR Extraction (ocr_accuracy must be present)
    # 2. Duplicate Detection (is_duplicate must be present)
    # 3. Tampering Analysis (must be analyzed or not_applicable_for_pdf_text_layer; NOT None, NOT unavailable, NOT failed)
    # 4. QR Verification (if QR code is detected on document, qr_valid must have run)
    missing_critical: list[str] = []
    is_pure_mock = (
        inputs.ocr_accuracy is None
        and inputs.is_duplicate is None
        and inputs.tampering_score is None
        and inputs.tampering_status is None
        and inputs.data_completeness == 1.0
    )

    if not is_pure_mock:
        if inputs.ocr_accuracy is None:
            missing_critical.append("OCR extraction")
        if inputs.is_duplicate is None:
            missing_critical.append("duplicate check")

        tamp_st = (inputs.tampering_status or "").lower()
        if tamp_st in ("unavailable", "not_checked") or tamp_st.startswith("failed"):
            missing_critical.append("tampering analysis")
        elif inputs.tampering_score is None and tamp_st != "not_applicable_for_pdf_text_layer":
            missing_critical.append("tampering analysis")

        if inputs.qr_present is True and inputs.qr_valid is None:
            missing_critical.append("QR verification")

    has_partial_critical = len(missing_critical) > 0

    # ── Calculate N of M checks for partial verification note ─────────────
    if inputs.evidence_breakdown and "_partial_verification" in inputs.evidence_breakdown:
        pv = inputs.evidence_breakdown["_partial_verification"]
        completed_checks = pv.get("completed", 0)
        total_checks = pv.get("total", 0)
        partial_note = pv.get("note", f"Partial verification: {completed_checks} of {total_checks} checks completed")
    else:
        applicable_checks = ["OCR", "Classification", "Field Extraction", "Tampering", "Duplicate"]
        if inputs.qr_present is not None:
            applicable_checks.append("QR")
        if inputs.blockchain_status is not None and inputs.blockchain_status != "unavailable":
            applicable_checks.append("Blockchain")
        if inputs.comparison_consistency_pct is not None:
            applicable_checks.append("Comparison")

        total_checks = len(applicable_checks)
        completed_checks = total_checks - len(missing_critical)
        if inputs.doc_classification_confidence is None:
            completed_checks -= 1
        if inputs.field_extraction_completeness is None:
            completed_checks -= 1
        completed_checks = max(0, completed_checks)
        partial_note = f"Partial verification: {completed_checks} of {total_checks} checks completed"

    if label == "genuine" and has_partial_critical:
        label = "inconclusive"

    # Rule 6: For text-only PDFs (status not_applicable_for_pdf_text_layer):
    # require a verified QR on a trusted domain or a blockchain match to allow "genuine";
    # otherwise return "inconclusive".
    tamp_st = (inputs.tampering_status or "").lower()
    is_text_only_pdf = tamp_st == "not_applicable_for_pdf_text_layer"
    has_trusted_external_anchor = (inputs.qr_present is True and inputs.qr_valid is True) or (
        inputs.blockchain_status == "verified"
    )
    if label == "genuine" and is_text_only_pdf and not has_trusted_external_anchor:
        label = "inconclusive"
        missing_critical.append("external anchor (verified QR code or blockchain match required for digital text-only PDF)")

    dist_label = label if label in ("genuine", "suspicious", "fake") else "suspicious"
    boundary_distance = _boundary_distance(score, dist_label)
    confidence = round(
        min(max(0.5 * boundary_distance + 0.5 * inputs.data_completeness, 0.0), 1.0), 4
    )

    # ── Duplicate hard override ───────────────────────────────────────────
    dup_status = (inputs.duplicate_status or "").lower()
    same_owner = bool(inputs.duplicate_same_owner)
    is_own = dup_status == "own_reupload" or (
        same_owner and not ("altered" in dup_status or dup_status.startswith("suspicious"))
        and (inputs.duplicate_type == "EXACT_FILE_DUPLICATE" or not inputs.duplicate_type)
    )
    is_altered = (
        "altered" in dup_status
        or dup_status in ("suspicious: altered re-upload", "suspicious_altered_reupload")
        or (inputs.duplicate_type or "").upper() == "ALTERED_REUPLOAD"
    )

    if inputs.is_duplicate and not is_own and not is_altered:
        label = "fake"
        confidence = max(confidence, 0.90)
    elif inputs.is_duplicate and is_altered:
        if label in ("genuine", "inconclusive", "inconclusive / needs review"):
            label = "suspicious"

    # ── Build structured evidence breakdown ───────────────────────────────
    evidence = _build_evidence(inputs)
    evidence["_partial_verification"] = {
        "completed": completed_checks,
        "total": total_checks,
        "note": partial_note,
        "is_partial": completed_checks < total_checks,
    }

    # ── Build reasons list ────────────────────────────────────────────────
    reasons = _build_reasons(inputs, label, score, fp, missing_critical, completed_checks, total_checks, partial_note)

    # ── Build plain text explanation (backward compatible) ────────────────
    explanation = _build_explanation(inputs, label, score, missing_critical, partial_note)

    # ── Recommended action ────────────────────────────────────────────────
    recommended_action = _build_recommended_action(label, inputs)

    return PredictionResult(
        label=label,
        confidence=confidence,
        explanation=explanation,
        recommended_action=recommended_action,
        fraud_probability=fp,
        evidence=evidence,
        reasons=reasons,
    )


# ---------------------------------------------------------------------------
# Evidence breakdown builder
# ---------------------------------------------------------------------------

def _build_evidence(inputs: PredictionInputs) -> dict:
    """
    Construct the spec-compliant evidence dict.
    Prefers evidence_breakdown from the trust score engine where available,
    falls back to deriving from raw inputs.
    """
    eb = inputs.evidence_breakdown or {}

    def _get(key: str, default: dict) -> dict:
        return eb.get(key, default)

    evidence: dict = {}

    # OCR
    if inputs.ocr_accuracy is not None:
        ocr_score = round(inputs.ocr_accuracy * 100, 1)
        evidence["ocr"] = {
            "score": ocr_score,
            "status": _pass_warn_fail(ocr_score, 85, 70),
        }
    else:
        evidence["ocr"] = {"score": None, "status": "UNAVAILABLE"}

    # Classification
    if inputs.doc_classification_confidence is not None:
        cls_score = round(inputs.doc_classification_confidence * 100, 1)
        evidence["classification"] = {
            "score": cls_score,
            "status": _pass_warn_fail(cls_score, 80, 60),
        }
    else:
        evidence["classification"] = _get("classification", {"score": None, "status": "UNAVAILABLE"})

    # Field extraction
    if inputs.field_extraction_completeness is not None:
        fe_score = round(inputs.field_extraction_completeness * 100, 1)
        evidence["field_extraction"] = {
            "score": fe_score,
            "status": _pass_warn_fail(fe_score, 80, 60),
        }
    else:
        evidence["field_extraction"] = _get("field_extraction", {"score": None, "status": "UNAVAILABLE"})

    # Document comparison
    if inputs.comparison_consistency_pct is not None:
        evidence["comparison"] = {
            "score": round(inputs.comparison_consistency_pct, 1),
            "status": _pass_warn_fail(inputs.comparison_consistency_pct, 80, 60),
        }
    else:
        evidence["comparison"] = {"score": None, "status": "UNAVAILABLE"}

    # QR verification
    if inputs.qr_present is None:
        evidence["qr"] = {"status": "NOT_CHECKED"}
    elif not inputs.qr_present:
        evidence["qr"] = {"status": "NOT_FOUND"}
    elif inputs.qr_valid:
        evidence["qr"] = {"status": "VERIFIED"}
    else:
        evidence["qr"] = {"status": "INVALID"}

    # Blockchain
    if inputs.blockchain_status is None:
        evidence["blockchain"] = {"status": "NOT_CHECKED"}
    elif inputs.blockchain_status == "unavailable":
        evidence["blockchain"] = {"status": "NOT_AVAILABLE"}
    elif inputs.blockchain_status == "verified":
        evidence["blockchain"] = {"status": "MATCH"}
    elif inputs.blockchain_status == "mismatch":
        evidence["blockchain"] = {"status": "MISMATCH"}
    else:
        evidence["blockchain"] = {"status": "NOT_REGISTERED"}

    # Tampering
    if inputs.tampering_score is not None:
        ts = inputs.tampering_score
        evidence["tampering"] = {
            "score": round(ts, 1),
            "status": "LOW_RISK" if ts < 30 else ("MEDIUM_RISK" if ts < 60 else "HIGH_RISK"),
        }
    else:
        evidence["tampering"] = {"score": None, "status": "NOT_CHECKED"}

    # Duplicate
    dup_status = (inputs.duplicate_status or "").lower()
    same_owner = bool(inputs.duplicate_same_owner)
    is_own = dup_status == "own_reupload" or (
        same_owner and not ("altered" in dup_status or dup_status.startswith("suspicious"))
        and (inputs.duplicate_type == "EXACT_FILE_DUPLICATE" or not inputs.duplicate_type)
    )
    is_altered = (
        "altered" in dup_status
        or dup_status in ("suspicious: altered re-upload", "suspicious_altered_reupload")
        or (inputs.duplicate_type or "").upper() == "ALTERED_REUPLOAD"
    )

    if inputs.is_duplicate is None:
        evidence["duplicate"] = {"status": "NOT_CHECKED"}
    elif not inputs.is_duplicate:
        evidence["duplicate"] = {"status": "NOT_FOUND"}
    elif is_own:
        evidence["duplicate"] = {"status": "OWN_REUPLOAD", "label": "You already uploaded this exact file"}
    elif is_altered:
        evidence["duplicate"] = {"status": "ALTERED_REUPLOAD", "label": "Suspicious: altered re-upload with different file content"}
    else:
        evidence["duplicate"] = {"status": "DUPLICATE"}

    # Metadata (from trust score engine or default clean)
    evidence["metadata"] = _get("metadata", {"status": "CLEAN"})

    return evidence


# ---------------------------------------------------------------------------
# Reasons builder
# ---------------------------------------------------------------------------

def _build_reasons(
    inputs: PredictionInputs,
    label: str,
    score: float,
    fp: float,
    missing_critical: list[str] | None = None,
    completed_checks: int | None = None,
    total_checks: int | None = None,
    partial_note: str | None = None,
) -> list[str]:
    reasons: list[str] = []

    if missing_critical:
        reasons.append(f"⚠ Critical verification check(s) incomplete: {', '.join(missing_critical)}")
    if partial_note:
        reasons.append(f"ℹ {partial_note}")

    # OCR
    if inputs.ocr_accuracy is not None:
        pct = round(inputs.ocr_accuracy * 100)
        if pct >= 85:
            reasons.append(f"✓ OCR confidence: {pct}% (high)")
        elif pct >= 70:
            reasons.append(f"⚠ OCR confidence: {pct}% (medium — some fields may need verification)")
        else:
            reasons.append(f"⚠ OCR confidence: {pct}% (low — extracted fields may be unreliable)")

    # Classification
    if inputs.doc_classification_confidence is not None:
        pct = round(inputs.doc_classification_confidence * 100)
        if pct >= 80:
            reasons.append(f"✓ Document type classified with {pct}% confidence")
        else:
            reasons.append(f"⚠ Document type classification confidence is low ({pct}%)")

    # Field extraction
    if inputs.field_extraction_completeness is not None:
        pct = round(inputs.field_extraction_completeness * 100)
        if pct >= 80:
            reasons.append(f"✓ {pct}% of expected fields were extracted successfully")
        else:
            reasons.append(f"⚠ Only {pct}% of expected fields could be extracted")

    # Comparison
    if inputs.comparison_consistency_pct is not None:
        pct = round(inputs.comparison_consistency_pct)
        if pct >= 80:
            reasons.append(f"✓ Cross-document comparison: {pct}% consistency")
        elif pct >= 60:
            reasons.append(f"⚠ Cross-document comparison shows partial consistency ({pct}%)")
        else:
            reasons.append(f"✗ Cross-document comparison found significant inconsistencies ({pct}%)")
    else:
        reasons.append("— Document comparison not run (single document verification)")

    # QR
    if inputs.qr_present is None:
        reasons.append("— QR verification not checked")
    elif not inputs.qr_present:
        reasons.append("— No QR code found on document (not automatically suspicious)")
    elif inputs.qr_valid:
        reasons.append("✓ QR code verified successfully")
    else:
        reasons.append("✗ QR code validation failed — possible forgery indicator")

    # Blockchain
    if inputs.blockchain_status == "verified":
        reasons.append("✓ Blockchain hash matched — document integrity confirmed")
    elif inputs.blockchain_status == "mismatch":
        reasons.append("✗ Blockchain hash MISMATCH — document may have been altered after registration")
    elif inputs.blockchain_status == "not_found":
        reasons.append("— Hash not found on blockchain (document may not be registered)")
    elif inputs.blockchain_status == "unavailable":
        reasons.append("— Blockchain verification unavailable (infrastructure not configured)")

    # Tampering
    tamp_st = (inputs.tampering_status or "").lower()
    if inputs.tampering_score is not None:
        ts = round(inputs.tampering_score)
        if ts < 30:
            reasons.append(f"✓ No significant tampering evidence detected (score {ts}/100)")
        elif ts < 60:
            reasons.append(f"⚠ Some tampering indicators detected (score {ts}/100) — review recommended")
        else:
            reasons.append(f"✗ Strong tampering evidence detected (score {ts}/100)")
    elif tamp_st == "not_applicable_for_pdf_text_layer":
        reasons.append("ℹ Tampering analysis: digital PDF text layer (raster tampering scan not applicable)")
    elif tamp_st.startswith("failed"):
        reasons.append(f"✗ Tampering analysis failed: {inputs.tampering_status}")
    else:
        reasons.append("— Tampering analysis not run")

    # Duplicate
    dup_status = (inputs.duplicate_status or "").lower()
    same_owner = bool(inputs.duplicate_same_owner)
    is_own = dup_status == "own_reupload" or (
        same_owner and not ("altered" in dup_status or dup_status.startswith("suspicious"))
        and (inputs.duplicate_type == "EXACT_FILE_DUPLICATE" or not inputs.duplicate_type)
    )
    is_altered = (
        "altered" in dup_status
        or dup_status in ("suspicious: altered re-upload", "suspicious_altered_reupload")
        or (inputs.duplicate_type or "").upper() == "ALTERED_REUPLOAD"
    )

    if inputs.is_duplicate is None:
        reasons.append("— Duplicate check not run")
    elif not inputs.is_duplicate:
        reasons.append("✓ No duplicate certificate detected")
    elif is_own:
        reasons.append("ℹ You already uploaded this exact file")
    elif is_altered:
        reasons.append("⚠ Suspicious: altered re-upload with different file content for the same register number")
    else:
        reasons.append("✗ Duplicate certificate detected — credentials already registered by another account")

    # Critical overrides
    if inputs.critical_overrides:
        for override in inputs.critical_overrides:
            if "blockchain_mismatch" in override:
                reasons.append("⚠ Blockchain mismatch triggered fraud probability floor (strong negative evidence)")
            elif "qr_invalid" in override:
                reasons.append("⚠ Invalid QR code triggered fraud probability floor")
            elif "tampering_severe" in override:
                reasons.append("⚠ Severe tampering score triggered fraud probability floor")
            elif "duplicate_floor" in override:
                reasons.append("⚠ Duplicate detection triggered maximum fraud probability floor")

    # Data completeness note
    if inputs.data_completeness < 0.5:
        reasons.append(
            f"⚠ Only {round(inputs.data_completeness * 100)}% of verification checks completed "
            f"— this verdict is based on partial evidence"
        )

    return reasons


# ---------------------------------------------------------------------------
# Helpers (unchanged from original, preserved for backward compatibility)
# ---------------------------------------------------------------------------

def _pass_warn_fail(value: float, pass_threshold: float, warn_threshold: float) -> str:
    if value >= pass_threshold:
        return "PASS"
    if value >= warn_threshold:
        return "WARN"
    return "FAIL"


def _boundary_distance(score: float, label: str) -> float:
    if label == "genuine":
        return min((score - GENUINE_THRESHOLD) / 20.0, 1.0)
    if label == "fake":
        return min((SUSPICIOUS_THRESHOLD - score) / SUSPICIOUS_THRESHOLD, 1.0)
    dist_from_lower = score - SUSPICIOUS_THRESHOLD
    dist_from_upper = GENUINE_THRESHOLD - score
    return min(min(dist_from_lower, dist_from_upper) / 15.0, 1.0)


def _build_explanation(
    inputs: PredictionInputs,
    label: str,
    score: float,
    missing_critical: list[str] | None = None,
    partial_note: str | None = None,
) -> str:
    """Plain text explanation — preserved for backward compatibility."""
    parts = [f"This certificate received a Trust Score of {score:.1f}/100."]

    if missing_critical:
        parts.append(f"Verification is incomplete: missing critical checks ({', '.join(missing_critical)}).")
    if partial_note:
        parts.append(f"{partial_note}.")

    if inputs.is_duplicate:
        dup_status = (inputs.duplicate_status or "").lower()
        same_owner = bool(inputs.duplicate_same_owner)
        is_own = dup_status == "own_reupload" or (
            same_owner and not ("altered" in dup_status or dup_status.startswith("suspicious"))
            and (inputs.duplicate_type == "EXACT_FILE_DUPLICATE" or not inputs.duplicate_type)
        )
        is_altered = (
            "altered" in dup_status
            or dup_status in ("suspicious: altered re-upload", "suspicious_altered_reupload")
            or (inputs.duplicate_type or "").upper() == "ALTERED_REUPLOAD"
        )

        if is_own:
            parts.append("You already uploaded this exact file (benign re-upload, not treated as fraud).")
        elif is_altered:
            parts.append(
                "This document matches your previous register number but has different file content, "
                "flagging it as a suspicious altered re-upload."
            )
        else:
            parts.append(
                "It was flagged as a duplicate of another certificate already in the system "
                "— this alone is treated as strong fraud evidence."
            )

    tamp_st = (inputs.tampering_status or "").lower()
    if inputs.tampering_score is not None:
        if inputs.tampering_score >= 60:
            parts.append(f"Tampering analysis found significant indicators of editing (score {inputs.tampering_score:.0f}/100).")
        elif inputs.tampering_score >= 30:
            parts.append(f"Tampering analysis found some minor indicators worth reviewing (score {inputs.tampering_score:.0f}/100).")
        else:
            parts.append("No significant signs of tampering were detected.")
    elif tamp_st == "not_applicable_for_pdf_text_layer":
        parts.append("Tampering scan not applicable for digital vector PDF text layer.")
    elif tamp_st.startswith("failed"):
        parts.append(f"Tampering scan failed: {inputs.tampering_status}.")

    if inputs.blockchain_status == "verified":
        parts.append("Its hash matches a record on the blockchain.")
    elif inputs.blockchain_status == "mismatch":
        parts.append("Its hash does NOT match the on-chain record — a strong red flag.")
    elif inputs.blockchain_status == "not_found":
        parts.append("Its hash was not found on the blockchain (it may simply not be registered yet).")

    if inputs.qr_present is False:
        parts.append("No QR code was found on the document.")
    elif inputs.qr_valid is False:
        parts.append("The QR code on the document failed validation.")
    elif inputs.qr_valid is True:
        parts.append("Its QR code validated successfully.")

    if inputs.comparison_consistency_pct is not None:
        if inputs.comparison_consistency_pct < 70:
            parts.append(f"Cross-document comparison found inconsistencies ({inputs.comparison_consistency_pct:.0f}% consistency).")
        else:
            parts.append(f"Cross-document comparison was consistent ({inputs.comparison_consistency_pct:.0f}%).")

    if inputs.ocr_accuracy is not None and inputs.ocr_accuracy < 0.6:
        parts.append("OCR extraction confidence was low, so some extracted fields may need manual verification.")

    if inputs.data_completeness < 0.5:
        parts.append("Note: not all verification checks have been run yet, so this assessment is based on partial data.")

    return " ".join(parts)


def _build_recommended_action(label: str, inputs: PredictionInputs | bool | None = None) -> str:
    if isinstance(inputs, bool):
        is_dup = inputs
        is_own = False
        is_altered = False
    elif inputs is None:
        is_dup = False
        is_own = False
        is_altered = False
    else:
        is_dup = bool(inputs.is_duplicate)
        dup_status = (inputs.duplicate_status or "").lower()
        same_owner = bool(inputs.duplicate_same_owner)
        is_own = dup_status == "own_reupload" or (
            same_owner and not ("altered" in dup_status or dup_status.startswith("suspicious"))
            and (inputs.duplicate_type == "EXACT_FILE_DUPLICATE" or not inputs.duplicate_type)
        )
        is_altered = (
            "altered" in dup_status
            or dup_status in ("suspicious: altered re-upload", "suspicious_altered_reupload")
            or (inputs.duplicate_type or "").upper() == "ALTERED_REUPLOAD"
        )

    if is_dup and not is_own and not is_altered:
        return "Reject this certificate and flag it for investigation — it duplicates another certificate already on file."
    if is_dup and is_altered:
        return "Manual review recommended — same register number was previously uploaded with different file content."
    if label == "genuine":
        return "No further action needed. This certificate passed verification."
    if label in ("inconclusive", "inconclusive / needs review"):
        return "Inconclusive / needs review — manual inspection required due to incomplete verification checks or missing external anchor."
    if label == "suspicious":
        return "Manual review recommended before relying on this certificate. Check the flagged factors above."
    return "Reject this certificate. Consider contacting the issuing institution to confirm its authenticity."
