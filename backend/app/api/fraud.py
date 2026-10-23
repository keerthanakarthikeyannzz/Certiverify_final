import asyncio
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.models import (
    User, Certificate, OCRData, DocumentComparison,
    VerificationResult, FraudAnalysis, DocumentType,
    VerificationJob, AuditLog
)
from app.schemas.fraud_schemas import FraudAnalysisResponse, SignalContribution
from app.services.fraud_analysis import (
    compute_fraud_analysis, FraudFactorInputs, FraudAnalysisResult
)
from app.services.image_quality import compute_image_quality_details
from app.services.tampering_detection import check_metadata
from app.services.storage_service import get_storage_backend
from app.services.image_preprocessing import load_image_as_array
from app.api.deps import get_current_verified_user

logger = logging.getLogger("certiverify.fraud")
router = APIRouter(prefix="/api/v1/certificates", tags=["Fraud Analysis"])

# Expected fields per OCR row for field_extraction_completeness
_OCR_TRACKABLE_FIELDS = [
    "student_name", "university_name", "register_number", "roll_number",
    "certificate_number", "department", "course", "cgpa", "percentage", "date_of_issue",
]


def _compute_field_completeness(ocr_row: OCRData | None) -> float | None:
    """Return fraction of tracked OCR fields that are non-None/non-empty."""
    if ocr_row is None:
        return None
    detected = sum(
        1 for f in _OCR_TRACKABLE_FIELDS
        if getattr(ocr_row, f, None) not in (None, "", 0)
    )
    return round(detected / len(_OCR_TRACKABLE_FIELDS), 4)


async def _gather_fraud_inputs(
    cert: Certificate,
    db: AsyncSession,
) -> tuple[FraudFactorInputs, dict]:
    """Gather all normalized verification signals from earlier stages."""
    ocr_result = await db.execute(select(OCRData).where(OCRData.certificate_id == cert.id))
    ocr_row = ocr_result.scalar_one_or_none()

    doc_type_result = await db.execute(select(DocumentType).where(DocumentType.certificate_id == cert.id))
    doc_type_row = doc_type_result.scalar_one_or_none()

    comparison_row = None
    if cert.group_id:
        comparison_result = await db.execute(
            select(DocumentComparison).where(DocumentComparison.group_id == cert.group_id)
        )
        comparison_row = comparison_result.scalar_one_or_none()

    verification_result = await db.execute(
        select(VerificationResult).where(VerificationResult.certificate_id == cert.id)
    )
    verification_row = verification_result.scalar_one_or_none()

    # Load file and compute image quality
    image_quality_details = None
    image_quality_score = None
    metadata_flags: list[str] = []

    try:
        storage = get_storage_backend()
        file_bytes = await storage.read(cert.storage_path)
        image = await asyncio.to_thread(load_image_as_array, file_bytes, cert.file_type)

        iq_details = await asyncio.to_thread(compute_image_quality_details, image)
        image_quality_details = iq_details
        image_quality_score = float(iq_details["overall_score"])

        metadata_flags = await asyncio.to_thread(check_metadata, file_bytes, cert.file_type)
    except Exception as exc:
        logger.warning("Could not read image or metadata for cert %s: %s", cert.id, exc)

    # If tampering analysis was already stored, reuse its metadata flags if richer
    if verification_row and verification_row.tampering_detail:
        td = verification_row.tampering_detail
        stored_meta = td.get("metadata_analysis", {})
        if stored_meta and stored_meta.get("flags"):
            for f in stored_meta["flags"]:
                if f not in metadata_flags:
                    metadata_flags.append(f)

    # Read duplicate details
    stored_dup_detail = {}
    if verification_row and getattr(verification_row, "duplicate_detail", None):
        stored_dup_detail = verification_row.duplicate_detail or {}

    inputs = FraudFactorInputs(
        # 1. OCR Accuracy & Field extraction
        ocr_accuracy=ocr_row.ocr_accuracy if ocr_row else None,
        field_confidences=ocr_row.field_confidences if (ocr_row and isinstance(ocr_row.field_confidences, dict)) else None,

        # 2. Cross-document comparison
        comparison_consistency_pct=comparison_row.consistency_percentage if comparison_row else None,

        # 3. QR code verification
        qr_present=verification_row.qr_present if verification_row else None,
        qr_valid=verification_row.qr_valid if verification_row else None,
        qr_warning=verification_row.qr_warning if verification_row else None,

        # 4. Blockchain verification
        blockchain_status=verification_row.blockchain_status if verification_row else None,
        blockchain_match=verification_row.blockchain_match if verification_row else None,

        # 5. Tampering score & risk level
        tampering_score=verification_row.tampering_score if verification_row else None,
        tampering_risk_level=verification_row.tampering_risk_level if verification_row else None,

        # 6. Duplicate detection
        is_duplicate=verification_row.is_duplicate if verification_row else None,
        duplicate_detail=stored_dup_detail,
        duplicate_type=stored_dup_detail.get("duplicate_type"),
        duplicate_status=stored_dup_detail.get("duplicate_status"),
        duplicate_same_owner=stored_dup_detail.get("same_owner"),

        # 7. Metadata integrity
        metadata_flags=metadata_flags,
        metadata_flags_present=len(metadata_flags) > 0,

        # 8. Image quality
        image_quality_score=image_quality_score,
        image_quality_details=image_quality_details,

        # Contextual indicators
        doc_classification_confidence=doc_type_row.confidence_score if doc_type_row else None,
        field_extraction_completeness=_compute_field_completeness(ocr_row),
        signature_present=ocr_row.has_signature if ocr_row else None,
        seal_present=ocr_row.has_seal if ocr_row else None,
    )

    return inputs, image_quality_details or {}


@router.post("/{certificate_id}/analyze-fraud", response_model=FraudAnalysisResponse)
@router.post("/{certificate_id}/fraud-analysis", response_model=FraudAnalysisResponse)
async def run_fraud_analysis(
    certificate_id: str,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Run MODULE 5 AI Fraud Analysis on a certificate.
    Synthesizes signals from OCR, Comparison, QR, Blockchain, Tampering, Duplicate,
    Metadata, and Image Quality into a normalized, explainable fraud probability.
    """
    cert = await _get_owned_certificate(certificate_id, user, db)
    inputs, iq_details = await _gather_fraud_inputs(cert, db)

    result: FraudAnalysisResult = await asyncio.to_thread(compute_fraud_analysis, inputs)

    # Persist or update FraudAnalysis table row
    existing = await db.execute(select(FraudAnalysis).where(FraudAnalysis.certificate_id == cert.id))
    fraud_row = existing.scalar_one_or_none()
    if fraud_row is None:
        fraud_row = FraudAnalysis(certificate_id=cert.id)
        db.add(fraud_row)

    fraud_row.fraud_probability          = result.fraud_probability
    fraud_row.ocr_accuracy_weight        = result.factor_weights.get("ocr_accuracy", 0.0)
    fraud_row.comparison_weight          = result.factor_weights.get("comparison", 0.0)
    fraud_row.qr_weight                  = result.factor_weights.get("qr", 0.0)
    fraud_row.blockchain_weight          = result.factor_weights.get("blockchain", 0.0)
    fraud_row.tampering_weight           = result.factor_weights.get("tampering", 0.0)
    fraud_row.duplicate_weight           = result.factor_weights.get("duplicate", 0.0)
    fraud_row.metadata_integrity_weight  = result.factor_weights.get("metadata_integrity", 0.0)
    fraud_row.image_quality_weight       = result.factor_weights.get("image_quality", 0.0)

    # Update verification_jobs stage_states if job exists
    job_res = await db.execute(
        select(VerificationJob)
        .where(VerificationJob.certificate_id == cert.id)
        .order_by(VerificationJob.id.desc())
    )
    job = job_res.scalars().first()
    if job:
        stage_states = dict(job.stage_states or {})
        stage_status = "FAILED" if result.fraud_probability >= 0.70 else "COMPLETED"
        fraud_summary = f"Fraud probability: {round(result.fraud_probability * 100, 1)}% [{result.risk_level}]"
        if result.critical_overrides_applied:
            fraud_summary += f" (Override: {', '.join(result.critical_overrides_applied)})"

        state_entry = {
            "status": stage_status,
            "label": "AI Fraud Analysis",
            "completed_at": datetime.utcnow().isoformat(),
            "details": fraud_summary,
        }
        stage_states["fraud_analysis"] = state_entry
        stage_states["FRAUD_ANALYSIS"] = state_entry
        job.stage_states = stage_states
        job.progress_percentage = max(job.progress_percentage or 0, 85)

    # Log audit event
    audit_entry = AuditLog(
        organization_id=cert.organization_id,
        actor_user_id=user.id,
        action="verification:fraud_analysis_completed",
        entity_type="certificate",
        entity_id=cert.id,
        metadata_json={
            "fraud_probability": result.fraud_probability,
            "risk_level": result.risk_level,
            "critical_overrides": result.critical_overrides_applied,
            "active_factors_count": len(result.factor_risks),
        },
    )
    db.add(audit_entry)

    # Emit evidence item
    try:
        from app.services.evidence_service import emit_fraud_evidence
        await emit_fraud_evidence(
            db=db,
            cert=cert,
            fraud_row=fraud_row,
            verification_job_id=job.id if job else None,
            actor_user_id=user.id,
            fraud_result_dict={
                "risk_level": result.risk_level,
                "factor_risks": result.factor_risks,
                "critical_overrides": result.critical_overrides_applied,
            },
        )
    except Exception as ev_err:
        logger.debug("Evidence emission skipped: %s", ev_err)

    await db.commit()
    await db.refresh(fraud_row)

    # Construct complete response with per-signal contribution breakdown
    response = FraudAnalysisResponse.model_validate(fraud_row)
    response.risk_level = result.risk_level
    response.factor_risks = result.factor_risks
    response.critical_overrides_applied = result.critical_overrides_applied
    response.image_quality_details = iq_details
    response.signal_contributions = [
        SignalContribution(**s.to_dict()) for s in result.signal_contributions
    ]
    return response


@router.get("/{certificate_id}/fraud-analysis", response_model=FraudAnalysisResponse)
@router.get("/{certificate_id}/fraud", response_model=FraudAnalysisResponse)
async def get_fraud_analysis(
    certificate_id: str,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve MODULE 5 AI Fraud Analysis for a certificate.
    Returns fraud_probability, per-factor weights, and full per-signal contribution breakdown.
    """
    cert = await _get_owned_certificate(certificate_id, user, db)
    result = await db.execute(select(FraudAnalysis).where(FraudAnalysis.certificate_id == cert.id))
    fraud_row = result.scalar_one_or_none()
    if not fraud_row:
        raise HTTPException(status_code=404, detail="No fraud analysis has been run on this certificate yet.")

    # Re-hydrate rich signal explanations and contributions
    inputs, iq_details = await _gather_fraud_inputs(cert, db)
    calc_res: FraudAnalysisResult = await asyncio.to_thread(compute_fraud_analysis, inputs)

    response = FraudAnalysisResponse.model_validate(fraud_row)
    response.risk_level = calc_res.risk_level
    response.factor_risks = calc_res.factor_risks
    response.critical_overrides_applied = calc_res.critical_overrides_applied
    response.image_quality_details = iq_details
    response.signal_contributions = [
        SignalContribution(**s.to_dict()) for s in calc_res.signal_contributions
    ]
    return response


async def _get_owned_certificate(certificate_id: str, user: User, db: AsyncSession) -> Certificate:
    from app.api.deps import get_owned_certificate
    return await get_owned_certificate(certificate_id, user, db)
