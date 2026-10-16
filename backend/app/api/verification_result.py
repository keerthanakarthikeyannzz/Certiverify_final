"""
MODULE 10b — UNIFIED VERIFICATION RESULT ENDPOINT

GET /api/v1/certificates/{id}/verification-result

Returns a single JSON response combining:
  - Trust Score
  - Fraud Probability
  - Final Prediction (label, confidence, explanation, recommended_action)
  - Structured evidence breakdown (per-factor PASS/WARN/FAIL/UNAVAILABLE)
  - Human-readable reasons list
  - Verification Summary (which checks have been run)

This replaces four separate API calls (fraud, trust, prediction, verification)
with one, reducing frontend latency and simplifying the UI data-fetching layer.

All data is READ-ONLY from the DB — it returns the last computed values.
To recompute, call the individual POST endpoints in order:
  analyze-fraud → compute-trust-score → predict
"""
from __future__ import annotations
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Any, Optional

from app.db.database import get_db
from app.models.models import (
    User, Certificate, OCRData, DocumentComparison, VerificationResult,
    FraudAnalysis, TrustScore, FinalPrediction, DocumentType,
)
from app.api.deps import get_current_verified_user
from app.services.final_prediction import (
    predict, PredictionInputs, _build_evidence, _build_reasons,
)

logger = logging.getLogger("certiverify.verification_result")

router = APIRouter(prefix="/api/v1/certificates", tags=["Verification Result"])

_OCR_TRACKABLE_FIELDS = [
    "student_name", "university_name", "register_number", "roll_number",
    "certificate_number", "department", "course", "cgpa", "percentage", "date_of_issue",
]


# ── Response schema ──────────────────────────────────────────────────────────

class VerificationSummary(BaseModel):
    document_type_identified: bool
    ocr_extracted: bool
    document_comparison_run: bool
    qr_checked: bool
    blockchain_checked: bool
    tampering_checked: bool
    duplicate_checked: bool
    fraud_analyzed: bool
    trust_score_computed: bool
    prediction_made: bool


class VerificationResultResponse(BaseModel):
    certificate_id: str
    trust_score: Optional[float] = None           # 0-100
    fraud_probability: Optional[float] = None     # 0-1
    prediction: Optional[str] = None             # "genuine" | "suspicious" | "fake"
    confidence: Optional[float] = None           # 0-1
    explanation: Optional[str] = None
    recommended_action: Optional[str] = None
    evidence: Optional[dict[str, Any]] = None    # per-factor structured breakdown
    reasons: Optional[list[str]] = None          # human-readable bullet list
    verification_summary: VerificationSummary
    data_completeness: float = 0.0               # 0-1, fraction of checks completed


# ── Endpoint ─────────────────────────────────────────────────────────────────

@router.get("/{certificate_id}/verification-result", response_model=VerificationResultResponse)
async def get_verification_result(
    certificate_id: str,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns the last computed verification decision for a certificate.
    Evidence and reasons are re-derived from stored scores if not persisted,
    ensuring the endpoint always returns the richest available data.
    """
    cert = await _get_owned_certificate(certificate_id, user, db)

    # Load all stored rows
    ocr_row         = await _fetch_one(db, OCRData,            OCRData.certificate_id == cert.id)
    doc_type_row    = await _fetch_one(db, DocumentType,       DocumentType.certificate_id == cert.id)
    verification_row= await _fetch_one(db, VerificationResult, VerificationResult.certificate_id == cert.id)
    fraud_row       = await _fetch_one(db, FraudAnalysis,      FraudAnalysis.certificate_id == cert.id)
    trust_row       = await _fetch_one(db, TrustScore,         TrustScore.certificate_id == cert.id)
    prediction_row  = await _fetch_one(db, FinalPrediction,    FinalPrediction.certificate_id == cert.id)

    comparison_row = None
    if cert.group_id:
        comparison_row = await _fetch_one(
            db, DocumentComparison, DocumentComparison.group_id == cert.group_id
        )

    # Build verification summary
    summary = VerificationSummary(
        document_type_identified=doc_type_row is not None,
        ocr_extracted=ocr_row is not None,
        document_comparison_run=comparison_row is not None,
        qr_checked=verification_row is not None and verification_row.qr_present is not None,
        blockchain_checked=verification_row is not None and verification_row.blockchain_status is not None,
        tampering_checked=verification_row is not None and verification_row.tampering_score is not None,
        duplicate_checked=verification_row is not None and verification_row.is_duplicate is not None,
        fraud_analyzed=fraud_row is not None,
        trust_score_computed=trust_row is not None,
        prediction_made=prediction_row is not None,
    )

    checks_done = sum([
        summary.ocr_extracted,
        summary.document_comparison_run,
        summary.qr_checked,
        summary.blockchain_checked,
        summary.tampering_checked,
        summary.duplicate_checked,
        summary.fraud_analyzed,
        summary.trust_score_computed,
    ])
    data_completeness = round(checks_done / 8, 4)

    # If no trust score yet, return partial summary
    if trust_row is None:
        return VerificationResultResponse(
            certificate_id=certificate_id,
            verification_summary=summary,
            data_completeness=data_completeness,
        )

    # Re-derive evidence + reasons from stored values
    field_completeness = _field_completeness(ocr_row)
    ts_breakdown       = trust_row.breakdown or {}
    evidence_breakdown = ts_breakdown.get("evidence_breakdown")

    dup_detail = (verification_row.duplicate_detail or {}) if verification_row else {}
    dup_status = dup_detail.get("duplicate_status")
    dup_same_owner = dup_detail.get("same_owner")
    dup_type = dup_detail.get("duplicate_type")
    dup_reason = verification_row.duplicate_match_reason if verification_row else None

    inputs = PredictionInputs(
        trust_score=trust_row.score,
        data_completeness=data_completeness,
        is_duplicate=verification_row.is_duplicate if verification_row else None,
        duplicate_status=dup_status,
        duplicate_same_owner=dup_same_owner,
        duplicate_type=dup_type,
        duplicate_match_reason=dup_reason,
        tampering_score=verification_row.tampering_score if verification_row else None,
        tampering_status=verification_row.tampering_status if verification_row else None,
        blockchain_status=verification_row.blockchain_status if verification_row else None,
        qr_present=verification_row.qr_present if verification_row else None,
        qr_valid=verification_row.qr_valid if verification_row else None,
        comparison_consistency_pct=comparison_row.consistency_percentage if comparison_row else None,
        fraud_probability=fraud_row.fraud_probability if fraud_row else None,
        ocr_accuracy=ocr_row.ocr_accuracy if ocr_row else None,
        doc_classification_confidence=doc_type_row.confidence_score if doc_type_row else None,
        field_extraction_completeness=field_completeness,
        evidence_breakdown=evidence_breakdown,
    )

    # Build evidence and reasons without re-classifying (use stored label)
    evidence = _build_evidence(inputs)
    label    = prediction_row.label.value if prediction_row else None
    reasons  = _build_reasons(inputs, label or "suspicious", trust_row.score,
                               fraud_row.fraud_probability if fraud_row else 0.0)

    logger.info(
        "Verification result | cert=%s | trust=%.1f | fraud=%.3f | label=%s | completeness=%.0f%%",
        certificate_id,
        trust_row.score,
        fraud_row.fraud_probability if fraud_row else 0.0,
        label,
        data_completeness * 100,
    )

    return VerificationResultResponse(
        certificate_id=certificate_id,
        trust_score=trust_row.score,
        fraud_probability=fraud_row.fraud_probability if fraud_row else None,
        prediction=label,
        confidence=prediction_row.confidence_score if prediction_row else None,
        explanation=prediction_row.explanation if prediction_row else None,
        recommended_action=prediction_row.recommended_action if prediction_row else None,
        evidence=evidence,
        reasons=reasons,
        verification_summary=summary,
        data_completeness=data_completeness,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _field_completeness(ocr_row) -> float | None:
    if ocr_row is None:
        return None
    detected = sum(
        1 for f in _OCR_TRACKABLE_FIELDS
        if getattr(ocr_row, f, None) not in (None, "", 0)
    )
    return round(detected / len(_OCR_TRACKABLE_FIELDS), 4)


async def _fetch_one(db: AsyncSession, model, condition):
    result = await db.execute(select(model).where(condition))
    return result.scalar_one_or_none()


async def _get_owned_certificate(certificate_id: str, user: User, db: AsyncSession) -> Certificate:
    result = await db.execute(
        select(Certificate).where(Certificate.id == certificate_id, Certificate.owner_id == user.id)
    )
    cert = result.scalar_one_or_none()
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found.")
    return cert
