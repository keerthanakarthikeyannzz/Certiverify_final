"""
MODULE 8 — TRUST SCORE ENGINE (Enhanced)

Produces a single 0-100 trust score from all available verification signals.

ENHANCEMENTS over original:
  - 2 new input signals: doc_classification_confidence, field_extraction_completeness
  - Weights realigned to match spec:
      OCR=15%, Classification=10%, Fields=10%, Comparison=15%,
      QR=10%, Blockchain=15%, Tampering=15%, Duplicate=5%, Metadata=5%
  - evidence_breakdown dict added to TrustScoreResult: per-factor status
    (PASS / WARN / FAIL / UNAVAILABLE) for structured JSON output
  - image_quality kept as a modifier (not a weighted factor) to keep total=100%

Unchanged from original:
  - Unavailable factors excluded and weights renormalized
  - Duplicate hard ceiling: if is_duplicate, score ≤ 15 (symmetric with fraud floor 0.85)
  - Pure score computation — classification into labels is Module 9's job
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class TrustScoreInputs:
    # ── Existing signals ────────────────────────────────────────────────────
    ocr_accuracy: float | None = None                   # 0-1
    image_quality_score: float | None = None            # 0-100, higher = better
    document_consistency_pct: float | None = None       # 0-100
    blockchain_status: str | None = None                # verified | not_found | mismatch | unavailable
    qr_present: bool | None = None
    qr_valid: bool | None = None
    tampering_score: float | None = None                # 0-100, higher = worse
    tampering_status: str | None = None                 # analyzed | not_applicable_for_pdf_text_layer | failed: <reason>
    is_duplicate: bool | None = None
    duplicate_status: str | None = None
    duplicate_same_owner: bool | None = None
    duplicate_type: str | None = None
    fraud_probability: float | None = None              # 0-1

    # ── New signals ─────────────────────────────────────────────────────────
    doc_classification_confidence: float | None = None  # 0-1
    field_extraction_completeness: float | None = None  # 0-1


@dataclass
class TrustScoreResult:
    score: float                                         # 0-100
    breakdown: dict = field(default_factory=dict)        # effective weight per factor
    factor_trust_values: dict = field(default_factory=dict)   # raw 0-100 trust per factor
    evidence_breakdown: dict = field(default_factory=dict)    # {factor: {score, status}}
    checks_completed: int = 0
    checks_total: int = 0
    partial_verification_note: str = ""


# Spec-aligned nominal weights (sum = 1.0)
NOMINAL_WEIGHTS: dict[str, float] = {
    "ocr_accuracy":              0.15,
    "doc_classification":        0.10,
    "field_extraction":          0.10,
    "document_consistency":      0.15,
    "qr":                        0.10,
    "blockchain":                0.15,
    "tampering":                 0.15,
    "duplicate":                 0.05,
    "fraud_probability":         0.05,
    # Note: image_quality is used as a modifier on OCR trust, not an independent factor
}


def _evidence_status(trust_value: float) -> str:
    """Map 0-100 trust value to a human-readable status string."""
    if trust_value >= 80:
        return "PASS"
    if trust_value >= 50:
        return "WARN"
    return "FAIL"


def compute_trust_score(inputs: TrustScoreInputs) -> TrustScoreResult:
    """
    Compute the 0-100 trust score from all available signals.

    Returns TrustScoreResult with score, per-factor breakdown, raw trust
    values, and a structured evidence_breakdown dict suitable for JSON output.
    """
    trust_values: dict[str, float] = {}
    evidence: dict[str, dict] = {}

    # ── 1. OCR accuracy ─────────────────────────────────────────────────────
    if inputs.ocr_accuracy is not None:
        base = round(inputs.ocr_accuracy * 100, 2)
        # Apply image quality modifier: high quality boosts slightly, poor quality dampens
        if inputs.image_quality_score is not None:
            quality_factor = 1.0 + 0.05 * ((inputs.image_quality_score - 50) / 50)
            base = round(min(max(base * quality_factor, 0), 100), 2)
        trust_values["ocr_accuracy"] = base
        evidence["ocr"] = {
            "score": base,
            "status": _evidence_status(base),
            "label": f"{base:.0f}% confidence",
        }

    # ── 2. Document classification ───────────────────────────────────────────
    if inputs.doc_classification_confidence is not None:
        val = round(inputs.doc_classification_confidence * 100, 2)
        trust_values["doc_classification"] = val
        evidence["classification"] = {
            "score": val,
            "status": _evidence_status(val),
            "label": f"{val:.0f}% confidence",
        }

    # ── 3. Field extraction completeness ────────────────────────────────────
    if inputs.field_extraction_completeness is not None:
        val = round(inputs.field_extraction_completeness * 100, 2)
        trust_values["field_extraction"] = val
        evidence["field_extraction"] = {
            "score": val,
            "status": _evidence_status(val),
            "label": f"{val:.0f}% fields extracted",
        }

    # ── 4. Document consistency ──────────────────────────────────────────────
    if inputs.document_consistency_pct is not None:
        val = round(min(max(inputs.document_consistency_pct, 0), 100), 2)
        trust_values["document_consistency"] = val
        evidence["comparison"] = {
            "score": val,
            "status": _evidence_status(val),
            "label": f"{val:.0f}% consistency",
        }
    else:
        evidence["comparison"] = {"score": None, "status": "UNAVAILABLE", "label": "Not run"}

    # ── 5. QR verification ───────────────────────────────────────────────────
    if inputs.qr_present is not None:
        if not inputs.qr_present:
            evidence["qr"] = {"score": None, "status": "no_qr_found", "label": "No QR code found"}
            # Absent QR code is not proof of fraud — excluded so it does not count as a failure
        elif inputs.qr_valid:
            qr_trust = 100.0
            qr_label = "VERIFIED"
            qr_status = "PASS"
            trust_values["qr"] = qr_trust
            evidence["qr"] = {"score": qr_trust, "status": qr_status, "label": qr_label}
        else:
            qr_trust = 0.0
            qr_label = "INVALID"
            qr_status = "FAIL"
            trust_values["qr"] = qr_trust
            evidence["qr"] = {"score": qr_trust, "status": qr_status, "label": qr_label}
    else:
        evidence["qr"] = {"score": None, "status": "no_qr_found", "label": "Not checked"}

    # ── 6. Blockchain verification ───────────────────────────────────────────
    if inputs.blockchain_status is not None and inputs.blockchain_status != "unavailable":
        blockchain_map = {
            "verified":  (100.0, "MATCH",       "PASS"),
            "not_found": (50.0,  "NOT_REGISTERED", "WARN"),
            "mismatch":  (0.0,   "MISMATCH",    "FAIL"),
        }
        bc_val, bc_label, bc_status = blockchain_map.get(
            inputs.blockchain_status, (50.0, inputs.blockchain_status, "WARN")
        )
        trust_values["blockchain"] = bc_val
        evidence["blockchain"] = {"score": bc_val, "status": bc_label, "display_status": bc_status}
    else:
        evidence["blockchain"] = {"score": None, "status": "NOT_AVAILABLE", "display_status": "UNAVAILABLE"}

    # ── 7. Tampering analysis ────────────────────────────────────────────────
    t_status = (inputs.tampering_status or "").lower()
    if t_status == "not_applicable_for_pdf_text_layer":
        evidence["tampering"] = {
            "score": None,
            "trust": None,
            "status": "not_applicable_for_pdf_text_layer",
            "display_status": "NOT_APPLICABLE",
            "label": "Not applicable for PDF text layer",
        }
    elif t_status.startswith("failed"):
        evidence["tampering"] = {
            "score": None,
            "trust": None,
            "status": inputs.tampering_status,
            "display_status": "FAILED",
            "label": inputs.tampering_status,
        }
    elif inputs.tampering_score is not None:
        tamp_trust = round(100.0 - min(max(inputs.tampering_score, 0), 100), 2)
        tamp_status = "PASS" if inputs.tampering_score < 30 else ("WARN" if inputs.tampering_score < 60 else "FAIL")
        trust_values["tampering"] = tamp_trust
        evidence["tampering"] = {
            "score": inputs.tampering_score,
            "trust": tamp_trust,
            "status": "LOW_RISK" if tamp_status == "PASS" else ("MEDIUM_RISK" if tamp_status == "WARN" else "HIGH_RISK"),
            "display_status": tamp_status,
            "label": "analyzed",
        }
    else:
        evidence["tampering"] = {"score": None, "status": "NOT_CHECKED", "display_status": "UNAVAILABLE", "label": "Unavailable"}

    # ── 8. Duplicate detection ───────────────────────────────────────────────
    if inputs.is_duplicate is not None:
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

        if not inputs.is_duplicate:
            dup_trust = 100.0
            evidence["duplicate"] = {
                "status": "NOT_FOUND",
                "display_status": "PASS",
                "label": "No duplicate record found",
            }
        elif is_own:
            # Re-upload of own file: informational only, no penalty
            dup_trust = 100.0
            evidence["duplicate"] = {
                "status": "OWN_REUPLOAD",
                "display_status": "PASS",
                "label": "You already uploaded this exact file",
            }
        elif is_altered:
            # Altered re-upload: moderate signal
            dup_trust = 50.0
            evidence["duplicate"] = {
                "status": "ALTERED_REUPLOAD",
                "display_status": "WARN",
                "label": "Suspicious: altered re-upload with different file content",
            }
        else:
            # Different owner / org duplicate -> strong fraud signal
            dup_trust = 0.0
            evidence["duplicate"] = {
                "status": "DUPLICATE",
                "display_status": "FAIL",
                "label": "Duplicate certificate detected from another account",
            }
        trust_values["duplicate"] = dup_trust
    else:
        evidence["duplicate"] = {"status": "NOT_CHECKED", "display_status": "UNAVAILABLE"}

    # ── 9. Fraud probability (integrated judgment) ───────────────────────────
    if inputs.fraud_probability is not None:
        fp_trust = round((1.0 - min(max(inputs.fraud_probability, 0), 1)) * 100, 2)
        trust_values["fraud_probability"] = fp_trust

    # ── No data at all ───────────────────────────────────────────────────────
    if not trust_values:
        return TrustScoreResult(
            score=50.0,
            breakdown={},
            factor_trust_values={},
            evidence_breakdown={
                **{k: {"score": None, "status": "UNAVAILABLE"} for k in NOMINAL_WEIGHTS},
            },
        )

    # ── Renormalized weighted average ────────────────────────────────────────
    total_nominal = sum(NOMINAL_WEIGHTS.get(f, 0.0) for f in trust_values)
    if total_nominal == 0:
        total_nominal = 1.0
    effective_weights = {
        f: NOMINAL_WEIGHTS.get(f, 0.0) / total_nominal for f in trust_values
    }
    score = sum(effective_weights[f] * trust_values[f] for f in trust_values)

    # ── Duplicate hard ceiling ────────────────────────────────────────────────
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
            pass  # Own re-upload is informational only: NO penalty, not fraud evidence
        elif is_altered:
            score = min(score, 65.0)  # Moderate ceiling (suspicious range, not fake)
        else:
            score = min(score, 15.0)  # Strong fraud evidence: force fake (< 15)

    # ── Critical evidence hard ceilings ──────────────────────────────────────
    # These mirror the fraud_analysis hard floors: a blockchain mismatch or
    # invalid QR is strong enough evidence that no matter how clean everything
    # else looks, the trust score cannot reach Genuine territory.
    if inputs.blockchain_status == "mismatch":
        score = min(score, 49.0)   # forces Fake band (< 50) on mismatch
    if inputs.qr_present and inputs.qr_valid is False:
        score = min(score, 64.0)   # forces at most Suspicious (< 65 is safer)
    if inputs.tampering_score is not None and inputs.tampering_score >= 70:
        score = min(score, 59.0)   # severe tampering → Suspicious at best

    score = round(min(max(score, 0.0), 100.0), 2)
    full_weights = {f: round(effective_weights.get(f, 0.0), 4) for f in NOMINAL_WEIGHTS}

    # Add metadata to evidence summary
    evidence["metadata"] = {
        "status": "CLEAN" if not _has_metadata_risk(inputs) else "FLAGGED",
        "display_status": "PASS" if not _has_metadata_risk(inputs) else "WARN",
    }

    # ── Partial verification calculation ─────────────────────────────────────
    applicable_checks = ["ocr", "classification", "field_extraction", "tampering", "duplicate"]
    if inputs.qr_present is not None:
        applicable_checks.append("qr")
    if inputs.blockchain_status is not None and inputs.blockchain_status != "unavailable":
        applicable_checks.append("blockchain")
    if inputs.document_consistency_pct is not None:
        applicable_checks.append("comparison")

    total_checks = len(applicable_checks)
    completed_checks = 0
    for chk in applicable_checks:
        ev = evidence.get(chk, {})
        st = str(ev.get("status", "")).lower()
        dst = str(ev.get("display_status", "")).upper()
        if st in ("unavailable", "not_checked", "not_available") or dst in ("UNAVAILABLE", "FAILED") or st.startswith("failed"):
            continue
        completed_checks += 1

    partial_note = f"Partial verification: {completed_checks} of {total_checks} checks completed"
    evidence["_partial_verification"] = {
        "completed": completed_checks,
        "total": total_checks,
        "note": partial_note,
        "is_partial": completed_checks < total_checks,
    }

    return TrustScoreResult(
        score=score,
        breakdown=full_weights,
        factor_trust_values=trust_values,
        evidence_breakdown=evidence,
        checks_completed=completed_checks,
        checks_total=total_checks,
        partial_verification_note=partial_note,
    )


def _has_metadata_risk(inputs: TrustScoreInputs) -> bool:
    """True if any signal suggests metadata-level risk."""
    if inputs.fraud_probability is not None and inputs.fraud_probability > 0.5:
        return True
    return False
