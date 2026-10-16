"""
MODULE 9 - FINAL PREDICTION API

POST /{certificate_id}/predict   -> gathers every available signal (via the
                                     already-computed Trust Score, plus the
                                     raw factors for a rich explanation) and
                                     classifies Genuine / Suspicious / Fake
GET  /{certificate_id}/prediction -> returns the last stored prediction
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.models import (
    User, Certificate, DocumentType, OCRData, DocumentComparison,
    VerificationResult, FraudAnalysis, TrustScore, FinalPrediction, PredictionLabel,
)
from datetime import datetime
from app.schemas.prediction_schemas import (
    FinalPredictionResponse, VerificationSummary,
    CertificateReviewRequest, CertificateReviewResponse,
)
from app.services.final_prediction import predict, PredictionInputs
from app.api.deps import get_current_verified_user

router = APIRouter(prefix="/api/v1/certificates", tags=["Final Prediction"])


@router.post("/{certificate_id}/review", response_model=CertificateReviewResponse)
async def submit_certificate_review(
    certificate_id: str,
    req: CertificateReviewRequest,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Persists manual reviewer decision ("genuine", "suspicious", "fake") and review notes
    against the actual certificate record in the database.
    """
    v_clean = req.verdict.lower().strip()
    if v_clean not in ("genuine", "suspicious", "fake"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid review verdict '{req.verdict}'. Must be genuine, suspicious, or fake."
        )

    cert = await _get_owned_certificate(certificate_id, user, db)

    pred_enum = (
        PredictionLabel.GENUINE if v_clean == "genuine" else
        PredictionLabel.SUSPICIOUS if v_clean == "suspicious" else
        PredictionLabel.FAKE
    )

    review_text = f"Manual Review Decision: {v_clean.upper()}."
    if req.review_note and req.review_note.strip():
        review_text += f" Review Note: {req.review_note.strip()}"

    prediction_row = await _fetch_one(db, FinalPrediction, FinalPrediction.certificate_id == cert.id)
    if prediction_row is None:
        prediction_row = FinalPrediction(
            certificate_id=cert.id,
            label=pred_enum,
            confidence_score=1.0,
            explanation=review_text,
            recommended_action=f"Reviewed & confirmed by verifier: {v_clean.upper()}",
        )
        db.add(prediction_row)
    else:
        prediction_row.label = pred_enum
        prediction_row.confidence_score = 1.0
        prediction_row.explanation = review_text
        prediction_row.recommended_action = f"Reviewed & confirmed by verifier: {v_clean.upper()}"
        prediction_row.created_at = datetime.utcnow()

    # Update TrustScore to align with reviewer verdict
    trust_row = await _fetch_one(db, TrustScore, TrustScore.certificate_id == cert.id)
    if trust_row is not None:
        if v_clean == "genuine":
            trust_row.score = max(trust_row.score, 90.0)
        elif v_clean == "suspicious":
            trust_row.score = min(trust_row.score, 55.0)
        elif v_clean == "fake":
            trust_row.score = 0.0

    await db.commit()
    await db.refresh(prediction_row)

    return CertificateReviewResponse(
        certificate_id=cert.id,
        verdict=v_clean,
        review_note=req.review_note,
        confidence_score=1.0,
        explanation=prediction_row.explanation,
        updated_at=prediction_row.created_at,
    )


@router.post("/{certificate_id}/predict", response_model=FinalPredictionResponse)
@router.post("/{certificate_id}/prediction", response_model=FinalPredictionResponse, include_in_schema=False)
async def run_prediction(
    certificate_id: str,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    cert = await _get_owned_certificate(certificate_id, user, db)

    doc_type_row = await _fetch_one(db, DocumentType, DocumentType.certificate_id == cert.id)
    ocr_row = await _fetch_one(db, OCRData, OCRData.certificate_id == cert.id)
    verification_row = await _fetch_one(db, VerificationResult, VerificationResult.certificate_id == cert.id)
    fraud_row = await _fetch_one(db, FraudAnalysis, FraudAnalysis.certificate_id == cert.id)
    if fraud_row is None:
        from app.api.fraud import run_fraud_analysis
        fraud_row = await run_fraud_analysis(certificate_id, user, db)

    trust_row = await _fetch_one(db, TrustScore, TrustScore.certificate_id == cert.id)
    if trust_row is None:
        from app.api.trust_score import run_trust_score
        trust_row = await run_trust_score(certificate_id, user, db)

    comparison_row = None
    if cert.group_id:
        comparison_row = await _fetch_one(db, DocumentComparison, DocumentComparison.group_id == cert.group_id)

    data_completeness = _compute_data_completeness(trust_row)

    # Pull evidence_breakdown stored by trust score engine
    ts_breakdown = trust_row.breakdown or {}
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
        # New signals
        doc_classification_confidence=doc_type_row.confidence_score if doc_type_row else None,
        field_extraction_completeness=_compute_field_completeness(ocr_row),
        evidence_breakdown=evidence_breakdown,
        critical_overrides=list(getattr(fraud_row, "_overrides", []) or []),
    )

    result = predict(inputs)

    existing = await db.execute(select(FinalPrediction).where(FinalPrediction.certificate_id == cert.id))
    prediction_row = existing.scalar_one_or_none()
    if prediction_row is None:
        prediction_row = FinalPrediction(certificate_id=cert.id)
        db.add(prediction_row)

    prediction_row.label              = PredictionLabel(result.label)
    prediction_row.confidence_score   = result.confidence
    prediction_row.explanation        = result.explanation
    prediction_row.recommended_action = result.recommended_action

    await db.commit()
    await db.refresh(prediction_row)

    response = FinalPredictionResponse.model_validate(prediction_row)
    response.fraud_probability      = result.fraud_probability
    response.evidence               = result.evidence
    response.reasons                = result.reasons
    response.verification_summary   = _build_summary(
        doc_type_row, ocr_row, comparison_row, verification_row, fraud_row, trust_row
    )
    return response


@router.get("/{certificate_id}/prediction", response_model=FinalPredictionResponse)
async def get_prediction(
    certificate_id: str,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    cert = await _get_owned_certificate(certificate_id, user, db)
    prediction_row = await _fetch_one(db, FinalPrediction, FinalPrediction.certificate_id == cert.id)
    if not prediction_row:
        raise HTTPException(status_code=404, detail="No prediction has been made for this certificate yet.")

    doc_type_row = await _fetch_one(db, DocumentType, DocumentType.certificate_id == cert.id)
    ocr_row = await _fetch_one(db, OCRData, OCRData.certificate_id == cert.id)
    verification_row = await _fetch_one(db, VerificationResult, VerificationResult.certificate_id == cert.id)
    fraud_row = await _fetch_one(db, FraudAnalysis, FraudAnalysis.certificate_id == cert.id)
    trust_row = await _fetch_one(db, TrustScore, TrustScore.certificate_id == cert.id)
    comparison_row = None
    if cert.group_id:
        comparison_row = await _fetch_one(db, DocumentComparison, DocumentComparison.group_id == cert.group_id)

    response = FinalPredictionResponse.model_validate(prediction_row)
    response.verification_summary = _build_summary(
        doc_type_row, ocr_row, comparison_row, verification_row, fraud_row, trust_row
    )
    return response


_OCR_TRACKABLE_FIELDS = [
    "student_name", "university_name", "register_number", "roll_number",
    "certificate_number", "department", "course", "cgpa", "percentage", "date_of_issue",
]


def _compute_field_completeness(ocr_row) -> float | None:
    if ocr_row is None:
        return None
    detected = sum(
        1 for f in _OCR_TRACKABLE_FIELDS
        if getattr(ocr_row, f, None) not in (None, "", 0)
    )
    return round(detected / len(_OCR_TRACKABLE_FIELDS), 4)


def _compute_data_completeness(trust_row: TrustScore) -> float:
    """Fraction of the 8 Trust Score factors that actually had data (non-zero weight)."""
    weights = (trust_row.breakdown or {}).get("weights", {})
    if not weights:
        return 0.0
    non_zero = sum(1 for w in weights.values() if w and w > 0)
    return round(non_zero / max(len(weights), 1), 4)


def _build_summary(doc_type_row, ocr_row, comparison_row, verification_row, fraud_row, trust_row) -> VerificationSummary:
    return VerificationSummary(
        document_type_identified=doc_type_row is not None,
        ocr_extracted=ocr_row is not None,
        document_comparison_run=comparison_row is not None,
        qr_checked=verification_row is not None and verification_row.qr_present is not None,
        blockchain_checked=verification_row is not None and verification_row.blockchain_status is not None,
        tampering_checked=verification_row is not None and verification_row.tampering_score is not None,
        duplicate_checked=verification_row is not None and verification_row.is_duplicate is not None,
        fraud_analyzed=fraud_row is not None,
        trust_score_computed=trust_row is not None,
    )


async def _fetch_one(db: AsyncSession, model, condition):
    result = await db.execute(select(model).where(condition))
    return result.scalar_one_or_none()


async def _get_owned_certificate(certificate_id: str, user: User, db: AsyncSession) -> Certificate:
    result = await db.execute(
        select(Certificate).where(Certificate.id == certificate_id)
    )
    cert = result.scalar_one_or_none()
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found.")

    from app.api.deps import verify_tenant_access
    verify_tenant_access(user, cert.organization_id, cert.owner_id)
    return cert
