"""
MODULE 7 — FINAL PREDICTION ENGINE (prediction)

Synthesizes the Trust Score, Fraud Probability, Evidence Coverage, and
Critical Hard-Override Flags into an institutional integrity verdict:
    - GENUINE
    - SUSPICIOUS
    - FAKE (LIKELY_FORGED)
    - INCONCLUSIVE

Key Principles:
1. Low-Coverage Protection: If evidence coverage is below a configurable minimum
   (default: 50% / 4 of 8 checks), the verdict is returned as INCONCLUSIVE
   rather than forcing a conclusive genuine/fake verdict.
2. Hard-Override Enforcement: Incontrovertible evidence of fraud (blockchain mismatch,
   unauthorized duplicate collision, or severe tampering >= 70) forces FAKE.
3. Threshold-Based Classification: Uses settings-configured trust and fraud thresholds.
4. Evidence-Grounded Explanation: Builds a plain-language explanation detailing
   which checks passed, which failed, and which were not evaluated.
5. Action Mapping: Maps each verdict label to a configurable operational recommendation.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional

from app.core.config import settings


@dataclass
class PredictionInputs:
    trust_score: float                                  # 0-100
    data_completeness: float = 0.0                      # 0-1, legacy completeness
    coverage: float | None = None                       # 0.0 - 1.0 (e.g. 0.75)
    checks_evaluated: int | None = None                 # e.g. 6
    checks_total: int | None = 8                        # 8
    is_duplicate: bool | None = None
    tampering_score: float | None = None                # 0-100
    tampering_status: str | None = None                 # analyzed | not_applicable_for_pdf_text_layer | failed: <reason> | unavailable
    tampering_risk_level: str | None = None
    blockchain_status: str | None = None
    blockchain_match: bool | None = None
    qr_present: bool | None = None
    qr_valid: bool | None = None
    qr_warning: str | None = None
    comparison_consistency_pct: float | None = None
    fraud_probability: float | None = None              # 0-1
    ocr_accuracy: float | None = None                  # 0-1
    duplicate_status: str | None = None
    duplicate_same_owner: bool | None = None
    duplicate_type: str | None = None
    duplicate_match_reason: str | None = None
    duplicate_detail: dict[str, Any] | None = None
    # Structured evidence and components from Trust Score engine
    evidence_breakdown: dict | None = None              # from TrustScoreResult.evidence_breakdown
    components: list[dict[str, Any]] | None = None      # itemized components list
    doc_classification_confidence: float | None = None  # 0-1
    field_extraction_completeness: float | None = None  # 0-1
    image_quality_score: float | None = None
    critical_overrides: list[str] | None = None         # from FraudAnalysisResult


@dataclass
class PredictionResult:
    label: str                                         # "genuine" | "suspicious" | "fake" | "inconclusive"
    confidence: float                                  # 0-1
    explanation: str                                   # plain language detailed explanation
    recommended_action: str
    fraud_probability: float = 0.0                    # 0-1
    trust_score: float = 0.0                          # 0-100
    coverage: float = 1.0                             # 0.0 - 1.0
    evidence: dict = field(default_factory=dict)       # structured per-factor JSON
    reasons: list[str] = field(default_factory=list)   # human-readable bullet sentences
    passed_checks: list[str] = field(default_factory=list)
    failed_checks: list[str] = field(default_factory=list)
    not_evaluated_checks: list[str] = field(default_factory=list)


def predict(inputs: PredictionInputs) -> PredictionResult:
    """
    Synthesize Trust Score, Fraud Probability, Coverage, and Hard Overrides into a final verdict.
    """
    score = float(inputs.trust_score)
    fp = float(inputs.fraud_probability if inputs.fraud_probability is not None else 0.0)

    # ── 1. Calculate Coverage ──
    checks_total = inputs.checks_total or 8
    if isinstance(inputs.coverage, dict):
        cov = float(inputs.coverage.get("ratio", 0.0))
        completed_checks = inputs.checks_evaluated or int(inputs.coverage.get("evaluated", round(cov * checks_total)))
        checks_total = int(inputs.coverage.get("total", checks_total))
    elif inputs.coverage is not None:
        cov = float(inputs.coverage)
        completed_checks = inputs.checks_evaluated or int(round(cov * checks_total))
    elif inputs.data_completeness > 0:
        cov = float(inputs.data_completeness)
        completed_checks = int(round(cov * checks_total))
    else:
        # Count available signals
        active_count = 0
        if inputs.ocr_accuracy is not None: active_count += 1
        if inputs.tampering_score is not None: active_count += 1
        if inputs.is_duplicate is not None: active_count += 1
        if inputs.qr_present is not None and inputs.qr_present: active_count += 1
        if inputs.blockchain_status not in (None, "unavailable", ""): active_count += 1
        if inputs.comparison_consistency_pct is not None: active_count += 1
        if inputs.fraud_probability is not None: active_count += 1
        if inputs.image_quality_score is not None: active_count += 1
        completed_checks = active_count
        cov = completed_checks / checks_total

    cov_percentage = round(cov * 100.0, 1)
    min_coverage = getattr(settings, "PREDICTION_MIN_COVERAGE_FOR_VERDICT", 0.50)

    # ── 2. Identify Hard Overrides & Critical Fraud Indicators ──
    hard_ceilings = list(inputs.critical_overrides or [])
    dup_status = (inputs.duplicate_status or "").lower()
    same_owner = bool(
        inputs.duplicate_same_owner
        or (inputs.duplicate_detail and inputs.duplicate_detail.get("same_owner"))
        or (inputs.duplicate_detail and inputs.duplicate_detail.get("owner_distinction") == "SAME_OWNER_REUPLOAD")
        or dup_status == "own_reupload"
    )
    is_altered = (
        "altered" in dup_status
        or (inputs.duplicate_type or "").upper() == "ALTERED_REUPLOAD"
        or (inputs.duplicate_detail and (inputs.duplicate_detail.get("duplicate_type") or "").upper() == "ALTERED_REUPLOAD")
    )

    is_confirmed_dup_collision = bool(inputs.is_duplicate and not same_owner and not is_altered)
    is_blockchain_mismatch = bool(inputs.blockchain_status == "mismatch" or inputs.blockchain_match is False)
    is_severe_tampering = bool(inputs.tampering_score is not None and inputs.tampering_score >= 70.0)
    is_invalid_qr = bool(inputs.qr_present is True and inputs.qr_valid is False)

    # ── 3. Decision Logic ──
    genuine_trust_min = getattr(settings, "PREDICTION_GENUINE_TRUST_MIN", 80.0)
    genuine_fraud_max = getattr(settings, "PREDICTION_GENUINE_FRAUD_MAX", 0.25)
    suspicious_trust_min = getattr(settings, "PREDICTION_SUSPICIOUS_TRUST_MIN", 50.0)
    suspicious_fraud_max = getattr(settings, "PREDICTION_SUSPICIOUS_FRAUD_MAX", 0.60)

    t_stat = (inputs.tampering_status or "").lower()
    is_tampering_unrun = (inputs.tampering_score is None) and (t_stat in ("unavailable", "unrun"))
    is_text_pdf_no_anchor = t_stat == "not_applicable_for_pdf_text_layer" and not (
        inputs.qr_valid is True or inputs.blockchain_status == "verified" or inputs.blockchain_match is True
    )

    # Conclusive fraud flags always force FAKE regardless of coverage
    if is_confirmed_dup_collision or is_blockchain_mismatch or is_severe_tampering:
        label = "fake"
        confidence = 0.95
    elif is_invalid_qr or is_altered:
        label = "suspicious"
        confidence = 0.85
    elif cov < min_coverage or is_tampering_unrun or is_text_pdf_no_anchor:
        # LOW COVERAGE GATE / CRITICAL CHECK MISSING: Insufficient evidence to render a definitive verdict
        label = "inconclusive"
        confidence = round(max(0.30, min(cov, 0.70)), 2)
    elif score >= genuine_trust_min and fp <= genuine_fraud_max:
        label = "genuine"
        # Confidence scales with trust score and coverage
        confidence = round(min(0.5 * (score / 100.0) + 0.3 * (1.0 - fp) + 0.2 * cov, 1.0), 2)
    elif score >= suspicious_trust_min and fp <= suspicious_fraud_max:
        label = "suspicious"
        confidence = round(min(0.70 + 0.25 * cov, 0.95), 2)
    else:
        label = "fake"
        confidence = round(min(0.5 * (1.0 - score / 100.0) + 0.5 * fp, 1.0), 2)

    # ── 4. Itemized Check Categorization (Passed / Failed / Not Evaluated) ──
    passed_checks, failed_checks, not_eval_checks = _categorize_checks(inputs)

    # ── 5. Build Structured Reasons List ──
    reasons = _build_reasons(inputs, label, score, fp)

    # ── 6. Build Plain Language Explanation ──
    explanation_parts = [
        f"Automated Verdict: {label.upper()} (Confidence: {round(confidence * 100)}%).",
        f"The certificate achieved an overall Trust Score of {score:.1f}/100 with an estimated AI fraud probability of {fp * 100:.1f}%.",
        f"Partial verification: {completed_checks} of {checks_total} verification checks evaluated ({cov_percentage}% coverage).",
    ]

    if passed_checks:
        explanation_parts.append(f"Verified Positive Evidence: {'; '.join(passed_checks)}.")
    if failed_checks:
        explanation_parts.append(f"Identified Risk Signals & Failures: {'; '.join(failed_checks)}.")
    if not_eval_checks:
        explanation_parts.append(f"Checks Excluded / Not Evaluated: {'; '.join(not_eval_checks)}.")

    if label in ("suspicious", "inconclusive"):
        explanation_parts.append(
            "Decision Support Advisory: This verdict is AI-generated decision support. A human compliance officer must review the findings before taking adverse action."
        )

    explanation = " ".join(explanation_parts)

    # ── 7. Map Recommended Operational Action ──
    recommended_action = _build_recommended_action(label)

    # ── 8. Build Evidence Breakdown ──
    evidence = _build_evidence(inputs)
    evidence["_partial_verification"] = {
        "completed": completed_checks,
        "total": checks_total,
        "coverage": cov,
        "coverage_percentage": cov_percentage,
        "is_partial": completed_checks < checks_total,
        "note": f"{completed_checks} of {checks_total} checks evaluated ({cov_percentage}% coverage)",
    }

    return PredictionResult(
        label=label,
        confidence=confidence,
        explanation=explanation,
        recommended_action=recommended_action,
        fraud_probability=fp,
        trust_score=score,
        coverage=cov,
        evidence=evidence,
        reasons=reasons,
        passed_checks=passed_checks,
        failed_checks=failed_checks,
        not_evaluated_checks=not_eval_checks,
    )


def _categorize_checks(inputs: PredictionInputs) -> tuple[list[str], list[str], list[str]]:
    passed_checks: list[str] = []
    failed_checks: list[str] = []
    not_eval_checks: list[str] = []

    # QR
    if inputs.qr_present is None or inputs.qr_present is False:
        not_eval_checks.append("QR Verification (no QR code on document)")
    elif inputs.qr_valid is True:
        passed_checks.append("QR Code cryptographic signature verified")
    elif inputs.qr_valid is False:
        failed_checks.append(f"QR Code validation failed ({inputs.qr_warning or 'invalid payload'})")
    else:
        failed_checks.append("QR Code warning (untrusted host/domain)")

    # Blockchain
    bc_st = (inputs.blockchain_status or "").lower()
    if bc_st in ("", "unavailable", "not_applicable", "skipped", "none"):
        not_eval_checks.append("Blockchain Verification (not configured/unavailable)")
    elif bc_st == "verified" or inputs.blockchain_match is True:
        passed_checks.append("Blockchain ledger cryptographic proof anchored")
    elif bc_st == "mismatch" or inputs.blockchain_match is False:
        failed_checks.append("Blockchain cryptographic hash MISMATCH against immutable record")
    elif bc_st == "not_found":
        not_eval_checks.append("Blockchain registry (document unanchored/not registered)")

    # OCR
    if inputs.ocr_accuracy is not None:
        pct = round(inputs.ocr_accuracy * 100, 1)
        if pct >= 80.0:
            passed_checks.append(f"OCR text extraction accuracy high ({pct}%)")
        elif pct >= 60.0:
            failed_checks.append(f"OCR text extraction accuracy moderate ({pct}%)")
        else:
            failed_checks.append(f"OCR text extraction accuracy low ({pct}%)")
    else:
        not_eval_checks.append("OCR extraction")

    # Tampering
    t_stat = (inputs.tampering_status or "").lower()
    if inputs.tampering_score is not None:
        ts_val = round(inputs.tampering_score, 1)
        if ts_val < 25.0:
            passed_checks.append(f"Tampering & ELA scan clean (tampering score {ts_val}/100 [LOW])")
        elif ts_val < 60.0:
            failed_checks.append(f"Tampering scan detected moderate anomalies ({ts_val}/100)")
        else:
            failed_checks.append(f"Severe tampering detected: ELA/font forgery score ({ts_val}/100 [HIGH RISK])")
    elif t_stat == "not_applicable_for_pdf_text_layer":
        not_eval_checks.append("Tampering scan (digital vector PDF text layer)")
    else:
        not_eval_checks.append("Tampering analysis")

    # Duplicate
    dup_status = (inputs.duplicate_status or "").lower()
    same_owner = bool(
        inputs.duplicate_same_owner
        or (inputs.duplicate_detail and inputs.duplicate_detail.get("same_owner"))
        or (inputs.duplicate_detail and inputs.duplicate_detail.get("owner_distinction") == "SAME_OWNER_REUPLOAD")
        or dup_status == "own_reupload"
    )
    is_altered = (
        "altered" in dup_status
        or (inputs.duplicate_type or "").upper() == "ALTERED_REUPLOAD"
        or (inputs.duplicate_detail and (inputs.duplicate_detail.get("duplicate_type") or "").upper() == "ALTERED_REUPLOAD")
    )

    if inputs.is_duplicate is not None:
        if not inputs.is_duplicate:
            passed_checks.append("Credential uniqueness confirmed (no duplicates in registry)")
        elif same_owner and not is_altered:
            passed_checks.append("Benign re-upload by original verified owner")
        elif is_altered:
            failed_checks.append("Suspicious altered re-upload (same register number, conflicting file content)")
        else:
            failed_checks.append("Duplicate credential collision with a different user account")
    else:
        not_eval_checks.append("Duplicate detection")

    # Fraud Analysis
    if inputs.fraud_probability is not None:
        fp_pct = round(inputs.fraud_probability * 100, 1)
        if fp_pct <= 25.0:
            passed_checks.append(f"AI Fraud probability low ({fp_pct}%)")
        elif fp_pct <= 50.0:
            failed_checks.append(f"AI Fraud probability moderate ({fp_pct}%)")
        else:
            failed_checks.append(f"AI Fraud probability high ({fp_pct}%)")
    else:
        not_eval_checks.append("AI Fraud Analysis")

    # Comparison
    if inputs.comparison_consistency_pct is not None:
        comp_pct = round(inputs.comparison_consistency_pct, 1)
        if comp_pct >= 80.0:
            passed_checks.append(f"Cross-document consistency high ({comp_pct}%)")
        else:
            failed_checks.append(f"Cross-document consistency low ({comp_pct}%)")
    else:
        not_eval_checks.append("Cross-document comparison (single upload)")

    # Image Quality
    if inputs.image_quality_score is not None:
        iq_val = round(inputs.image_quality_score, 1)
        if iq_val >= 70.0:
            passed_checks.append(f"Scan fidelity & resolution high ({iq_val}/100)")
        else:
            failed_checks.append(f"Scan quality degraded or low contrast ({iq_val}/100)")
    else:
        not_eval_checks.append("Scan image quality")

    return passed_checks, failed_checks, not_eval_checks


def _build_reasons(
    inputs: PredictionInputs,
    label: str,
    trust_score: float = 0.0,
    fraud_probability: float = 0.0,
) -> list[str]:
    passed_checks, failed_checks, not_eval_checks = _categorize_checks(inputs)
    reasons: list[str] = []

    checks_total = inputs.checks_total or 8
    if isinstance(inputs.coverage, dict):
        cov = float(inputs.coverage.get("ratio", 0.0))
        completed_checks = inputs.checks_evaluated or int(inputs.coverage.get("evaluated", round(cov * checks_total)))
        checks_total = int(inputs.coverage.get("total", checks_total))
    elif inputs.coverage is not None:
        cov = float(inputs.coverage)
        completed_checks = inputs.checks_evaluated or int(round(cov * checks_total))
    elif inputs.data_completeness > 0:
        cov = float(inputs.data_completeness)
        completed_checks = int(round(cov * checks_total))
    else:
        completed_checks = len(passed_checks) + len(failed_checks)
        cov = completed_checks / checks_total

    cov_percentage = round(cov * 100.0, 1)
    min_coverage = getattr(settings, "PREDICTION_MIN_COVERAGE_FOR_VERDICT", 0.50)

    if label.lower() == "inconclusive":
        reasons.append(
            f"ℹ Inconclusive verdict: Evidence coverage is {cov_percentage}% ({completed_checks} of {checks_total} checks evaluated), "
            f"which is below the required {round(min_coverage * 100)}% threshold for an automated conclusive verdict."
        )

    if completed_checks < checks_total:
        reasons.append(
            f"Partial verification: {completed_checks} of {checks_total} checks completed ({cov_percentage}% coverage)."
        )

    for p in passed_checks:
        reasons.append(f"✓ {p}")
    for f in failed_checks:
        reasons.append(f"✗ {f}")
    for n in not_eval_checks:
        reasons.append(f"— Not evaluated: {n}")

    return reasons


def _build_recommended_action(label: str) -> str:
    lbl = (label or "").lower().strip()
    if "genuine" in lbl:
        return getattr(
            settings,
            "PREDICTION_ACTION_GENUINE",
            "Accept certificate — credential verified against institutional and forensic standards."
        )
    elif "inconclusive" in lbl:
        return getattr(
            settings,
            "PREDICTION_ACTION_INCONCLUSIVE",
            "Request original hardcopy or direct verification from the issuing institution (insufficient evidence coverage / inconclusive)."
        )
    elif "suspicious" in lbl:
        return getattr(
            settings,
            "PREDICTION_ACTION_SUSPICIOUS",
            "Manual review required — escalate to admissions/compliance officer for secondary inspection."
        )
    else: # fake / likely_forged
        return getattr(
            settings,
            "PREDICTION_ACTION_FAKE",
            "Reject certificate — evidence indicates tampering, credential collision, or cryptographic forgery."
        )


def _build_evidence(inputs: PredictionInputs) -> dict:
    eb = inputs.evidence_breakdown or {}

    def _get(key: str, default: dict) -> dict:
        return eb.get(key, default)

    evidence: dict = {}

    # OCR
    if inputs.ocr_accuracy is not None:
        ocr_score = round(inputs.ocr_accuracy * 100, 1)
        evidence["ocr"] = {"score": ocr_score, "status": "PASS" if ocr_score >= 80 else ("WARN" if ocr_score >= 60 else "FAIL")}
    else:
        evidence["ocr"] = {"score": None, "status": "UNAVAILABLE"}

    # Classification
    if inputs.doc_classification_confidence is not None:
        cls_score = round(inputs.doc_classification_confidence * 100, 1)
        evidence["classification"] = {"score": cls_score, "status": "PASS" if cls_score >= 80 else ("WARN" if cls_score >= 60 else "FAIL")}
    else:
        evidence["classification"] = _get("classification", {"score": None, "status": "UNAVAILABLE"})

    # Field extraction
    if inputs.field_extraction_completeness is not None:
        fe_score = round(inputs.field_extraction_completeness * 100, 1)
        evidence["field_extraction"] = {"score": fe_score, "status": "PASS" if fe_score >= 80 else ("WARN" if fe_score >= 60 else "FAIL")}
    else:
        evidence["field_extraction"] = _get("field_extraction", {"score": None, "status": "UNAVAILABLE"})

    # Comparison
    if inputs.comparison_consistency_pct is not None:
        evidence["comparison"] = {"score": round(inputs.comparison_consistency_pct, 1), "status": "PASS" if inputs.comparison_consistency_pct >= 80 else "FAIL"}
    else:
        evidence["comparison"] = {"score": None, "status": "UNAVAILABLE"}

    # QR
    if inputs.qr_present is None:
        evidence["qr"] = {"status": "NOT_CHECKED"}
    elif not inputs.qr_present:
        evidence["qr"] = {"status": "NOT_FOUND"}
    elif inputs.qr_valid:
        evidence["qr"] = {"status": "VERIFIED"}
    else:
        evidence["qr"] = {"status": "INVALID"}

    # Blockchain
    bc = (inputs.blockchain_status or "").lower()
    if bc in ("", "unavailable"):
        evidence["blockchain"] = {"status": "NOT_AVAILABLE"}
    elif bc == "verified":
        evidence["blockchain"] = {"status": "MATCH"}
    elif bc == "mismatch":
        evidence["blockchain"] = {"status": "MISMATCH"}
    else:
        evidence["blockchain"] = {"status": "NOT_REGISTERED"}

    # Tampering
    if inputs.tampering_score is not None:
        ts = inputs.tampering_score
        evidence["tampering"] = {
            "score": round(ts, 1),
            "status": "LOW_RISK" if ts < 25 else ("MEDIUM_RISK" if ts < 60 else "HIGH_RISK"),
        }
    else:
        evidence["tampering"] = {"score": None, "status": "NOT_CHECKED"}

    # Duplicate
    same_owner = bool(inputs.duplicate_same_owner)
    dup_st = (inputs.duplicate_status or "").lower()
    is_own = dup_st == "own_reupload" or same_owner
    if inputs.is_duplicate is None:
        evidence["duplicate"] = {"status": "NOT_CHECKED"}
    elif not inputs.is_duplicate:
        evidence["duplicate"] = {"status": "NOT_FOUND"}
    elif is_own:
        evidence["duplicate"] = {"status": "OWN_REUPLOAD"}
    else:
        evidence["duplicate"] = {"status": "DUPLICATE"}

    evidence["metadata"] = _get("metadata", {"status": "CLEAN"})
    return evidence
