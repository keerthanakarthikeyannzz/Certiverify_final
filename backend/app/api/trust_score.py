import asyncio
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.models import (
    User, Certificate, OCRData, DocumentComparison, VerificationResult,
    FraudAnalysis, TrustScore, DocumentType, VerificationJob, AuditLog
)
from app.schemas.trust_score_schemas import TrustScoreResponse, TrustComponentBreakdown
from app.services.trust_score import compute_trust_score, TrustScoreInputs, TrustScoreResult
from app.services.image_quality import compute_image_quality_details
from app.services.storage_service import get_storage_backend
from app.services.image_preprocessing import load_image_as_array
from app.api.deps import get_current_verified_user, verify_tenant_access

logger = logging.getLogger("certiverify.trust_score")
router = APIRouter(prefix="/api/v1/certificates", tags=["Trust Score"])

_OCR_TRACKABLE_FIELDS = [
    "student_name", "university_name", "register_number", "roll_number",
    "certificate_number", "department", "course", "cgpa", "percentage", "date_of_issue",
]


def _compute_field_completeness(ocr_row: OCRData | None) -> float | None:
    if ocr_row is None:
        return None
    detected = sum(
        1 for f in _OCR_TRACKABLE_FIELDS
        if getattr(ocr_row, f, None) not in (None, "", 0)
    )
    return round(detected / len(_OCR_TRACKABLE_FIELDS), 4)


async def _gather_trust_score_inputs(cert: Certificate, db: AsyncSession) -> tuple[TrustScoreInputs, dict]:
    """Gather all 8 verification signals for Trust Score calculation."""
    ocr_result = await db.execute(
        select(OCRData).where(OCRData.certificate_id == cert.id).order_by(OCRData.id.desc())
    )
    ocr_row = ocr_result.scalars().first()

    doc_type_result = await db.execute(
        select(DocumentType).where(DocumentType.certificate_id == cert.id).order_by(DocumentType.id.desc())
    )
    doc_type_row = doc_type_result.scalars().first()

    comparison_row = None
    if cert.group_id:
        comparison_result = await db.execute(
            select(DocumentComparison).where(DocumentComparison.group_id == cert.group_id).order_by(DocumentComparison.id.desc())
        )
        comparison_row = comparison_result.scalars().first()

    verification_result = await db.execute(
        select(VerificationResult).where(VerificationResult.certificate_id == cert.id).order_by(VerificationResult.id.desc())
    )
    verification_row = verification_result.scalars().first()

    fraud_result = await db.execute(
        select(FraudAnalysis).where(FraudAnalysis.certificate_id == cert.id).order_by(FraudAnalysis.id.desc())
    )
    fraud_row = fraud_result.scalars().first()

    image_quality_details = None
    image_quality_score = None
    try:
        storage = get_storage_backend()
        file_bytes = await storage.read(cert.storage_path)
        image = await asyncio.to_thread(load_image_as_array, file_bytes, cert.file_type)
        iq_details = await asyncio.to_thread(compute_image_quality_details, image)
        image_quality_details = iq_details
        image_quality_score = float(iq_details["overall_score"])
    except Exception as exc:
        logger.warning("Could not read image for trust score image_quality on cert %s: %s", cert.id, exc)

    dup_detail = (verification_row.duplicate_detail or {}) if verification_row else {}
    dup_status = dup_detail.get("duplicate_status")
    dup_same_owner = dup_detail.get("same_owner")
    dup_type = dup_detail.get("duplicate_type")

    inputs = TrustScoreInputs(
        # 1. OCR Accuracy & Field Completeness
        ocr_accuracy=ocr_row.ocr_accuracy if ocr_row else None,
        field_confidences=ocr_row.field_confidences if (ocr_row and isinstance(ocr_row.field_confidences, dict)) else None,
        field_extraction_completeness=_compute_field_completeness(ocr_row),
        doc_classification_confidence=(doc_type_row.confidence_score if doc_type_row else None),

        # 2. Cross-document comparison
        document_consistency_pct=comparison_row.consistency_percentage if comparison_row else None,

        # 3. QR verification
        qr_present=verification_row.qr_present if verification_row else None,
        qr_valid=verification_row.qr_valid if verification_row else None,
        qr_warning=verification_row.qr_warning if verification_row else None,

        # 4. Blockchain verification
        blockchain_status=verification_row.blockchain_status if verification_row else None,
        blockchain_match=verification_row.blockchain_match if verification_row else None,

        # 5. Tampering detection
        tampering_score=verification_row.tampering_score if verification_row else None,
        tampering_status=verification_row.tampering_status if verification_row else None,
        tampering_risk_level=verification_row.tampering_risk_level if verification_row else None,

        # 6. Duplicate detection
        is_duplicate=verification_row.is_duplicate if verification_row else None,
        duplicate_status=dup_status,
        duplicate_same_owner=dup_same_owner,
        duplicate_type=dup_type,
        duplicate_detail=dup_detail,

        # 7. AI Fraud probability
        fraud_probability=fraud_row.fraud_probability if fraud_row else None,

        # 8. Image quality
        image_quality_score=image_quality_score,
        image_quality_details=image_quality_details,
    )

    return inputs, image_quality_details or {}


@router.post("/{certificate_id}/compute-trust-score", response_model=TrustScoreResponse)
@router.post("/{certificate_id}/trust-score", response_model=TrustScoreResponse)
async def run_trust_score(
    certificate_id: str,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Run MODULE 6 Trust Score stage on a certificate.
    Computes an explainable, monotonic 0-100 Trust Score from positive evidence
    and AI fraud analysis, returning breakdown and coverage metrics.
    """
    cert = await _get_owned_certificate(certificate_id, user, db)
    inputs, _ = await _gather_trust_score_inputs(cert, db)

    result: TrustScoreResult = await asyncio.to_thread(compute_trust_score, inputs)

    # Persist or update TrustScore record
    existing = await db.execute(
        select(TrustScore).where(TrustScore.certificate_id == cert.id).order_by(TrustScore.id.desc())
    )
    trust_row = existing.scalars().first()
    if trust_row is None:
        trust_row = TrustScore(certificate_id=cert.id)
        db.add(trust_row)

    trust_row.score = result.score
    trust_row.breakdown = result.breakdown

    # Update verification_jobs stage_states if job exists
    job_res = await db.execute(
        select(VerificationJob)
        .where(VerificationJob.certificate_id == cert.id)
        .order_by(VerificationJob.id.desc())
    )
    job = job_res.scalars().first()
    if job:
        stage_states = dict(job.stage_states or {})
        stage_summary = (
            f"Trust Score: {result.score}/100 [{result.band_label}], "
            f"Coverage: {result.checks_evaluated}/{result.checks_total} ({result.coverage_percentage}%)"
        )
        state_entry = {
            "status": "COMPLETED",
            "label": "Trust Score Calculation",
            "completed_at": datetime.utcnow().isoformat(),
            "details": stage_summary,
        }
        stage_states["trust_score"] = state_entry
        stage_states["TRUST_SCORE"] = state_entry
        job.stage_states = stage_states
        job.progress_percentage = max(job.progress_percentage or 0, 92)

    # Log audit event
    audit_entry = AuditLog(
        organization_id=cert.organization_id,
        actor_user_id=user.id,
        action="verification:trust_score_completed",
        entity_type="certificate",
        entity_id=cert.id,
        metadata_json={
            "trust_score": result.score,
            "band": result.band,
            "coverage": result.coverage,
            "checks_evaluated": result.checks_evaluated,
            "checks_total": result.checks_total,
        },
    )
    db.add(audit_entry)

    # Emit evidence item
    try:
        from app.services.evidence_service import emit_trust_score_evidence
        await emit_trust_score_evidence(
            db=db,
            cert=cert,
            trust_row=trust_row,
            verification_job_id=job.id if job else None,
            actor_user_id=user.id,
            trust_result_dict=result.breakdown,
        )
    except Exception as ev_err:
        logger.debug("Trust score evidence emission skipped: %s", ev_err)

    await db.commit()
    await db.refresh(trust_row)

    response = TrustScoreResponse(
        id=trust_row.id,
        certificate_id=trust_row.certificate_id,
        score=result.score,
        band=result.band,
        band_label=result.band_label,
        coverage=result.coverage,
        coverage_percentage=result.coverage_percentage,
        checks_evaluated=result.checks_evaluated,
        checks_total=result.checks_total,
        components=[TrustComponentBreakdown(**c.to_dict()) for c in result.components],
        breakdown=result.breakdown,
        created_at=trust_row.created_at or datetime.utcnow(),
    )
    return response


@router.get("/{certificate_id}/trust-score", response_model=TrustScoreResponse)
async def get_trust_score(
    certificate_id: str,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve MODULE 6 Trust Score for a certificate.
    Returns score, band, coverage metrics, and detailed component breakdown.
    """
    cert = await _get_owned_certificate(certificate_id, user, db)
    result = await db.execute(
        select(TrustScore).where(TrustScore.certificate_id == cert.id).order_by(TrustScore.id.desc())
    )
    trust_row = result.scalars().first()
    if not trust_row:
        raise HTTPException(status_code=404, detail="No trust score has been computed for this certificate yet.")

    bd = trust_row.breakdown or {}
    cov = bd.get("coverage", {})

    # Reconstruct or rehydrate components if present
    comps_data = bd.get("components")
    components_list = None
    if comps_data and isinstance(comps_data, list):
        components_list = [TrustComponentBreakdown(**c) for c in comps_data]
    else:
        # Re-compute if legacy format in DB
        inputs, _ = await _gather_trust_score_inputs(cert, db)
        fresh_res: TrustScoreResult = await asyncio.to_thread(compute_trust_score, inputs)
        return TrustScoreResponse(
            id=trust_row.id,
            certificate_id=trust_row.certificate_id,
            score=trust_row.score,
            band=fresh_res.band,
            band_label=fresh_res.band_label,
            coverage=fresh_res.coverage,
            coverage_percentage=fresh_res.coverage_percentage,
            checks_evaluated=fresh_res.checks_evaluated,
            checks_total=fresh_res.checks_total,
            components=[TrustComponentBreakdown(**c.to_dict()) for c in fresh_res.components],
            breakdown=fresh_res.breakdown,
            created_at=trust_row.created_at or datetime.utcnow(),
        )

    band = bd.get("band", "HIGH" if trust_row.score >= 80 else ("MEDIUM" if trust_row.score >= 50 else "LOW"))
    band_label = bd.get("band_label", "High Trust" if band == "HIGH" else ("Medium Trust" if band == "MEDIUM" else "Low Trust"))
    coverage = cov.get("ratio", 1.0)
    cov_pct = cov.get("percentage", 100.0)
    evaluated = cov.get("evaluated", 8)
    total = cov.get("total", 8)

    return TrustScoreResponse(
        id=trust_row.id,
        certificate_id=trust_row.certificate_id,
        score=trust_row.score,
        band=band,
        band_label=band_label,
        coverage=coverage,
        coverage_percentage=cov_pct,
        checks_evaluated=evaluated,
        checks_total=total,
        components=components_list,
        breakdown=bd,
        created_at=trust_row.created_at or datetime.utcnow(),
    )


async def _get_owned_certificate(certificate_id: str, user: User, db: AsyncSession) -> Certificate:
    from app.api.deps import get_owned_certificate
    return await get_owned_certificate(certificate_id, user, db)
