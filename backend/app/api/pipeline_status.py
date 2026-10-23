"""
PRIORITY 8 - VERIFICATION PIPELINE STATUS

Single endpoint that returns the per-stage completion state of an entire
verification pipeline for a certificate, sourcing data from existing tables.

GET /api/v1/certificates/{certificate_id}/pipeline

Each stage reports:
  stage       : str   — stage key name
  label       : str   — human-readable label
  status      : str   — COMPLETED | PENDING | FAILED | UNAVAILABLE
  completed_at: str | None
  summary     : str | None   — brief one-liner (e.g. "OCR: 94%")
  duration_ms : int | None   — processing time hint where available
"""
from __future__ import annotations

from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.database import get_db
from app.models.models import (
    Certificate, DocumentComparison, DocumentType, FinalPrediction,
    FraudAnalysis, OCRData, TrustScore, User, VerificationReport,
    VerificationResult,
)
from app.api.deps import get_current_verified_user, get_owned_certificate, normalize_cert_id
import logging

logger = logging.getLogger("certiverify.pipeline_status")

router = APIRouter(tags=["Pipeline Status"])

COMPLETED   = "COMPLETED"
PENDING     = "PENDING"
FAILED      = "FAILED"
UNAVAILABLE = "UNAVAILABLE"


class PipelineStage(BaseModel):
    stage: str
    label: str
    status: str                     # COMPLETED | PENDING | FAILED | UNAVAILABLE
    completed_at: Optional[str] = None
    summary: Optional[str] = None
    duration_ms: Optional[int] = None


class PipelineStatusResponse(BaseModel):
    certificate_id: str
    filename: str
    file_type: str
    uploaded_at: str
    overall_status: str             # FULLY_COMPLETE | PARTIALLY_COMPLETE | NOT_STARTED | PROCESSING
    completion_pct: float           # 0-100
    stages: list[PipelineStage]
    job_id: Optional[str] = None


def _ts(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _stage(stage: str, label: str, completed: bool,
           completed_at: Optional[datetime] = None,
           summary: Optional[str] = None) -> PipelineStage:
    return PipelineStage(
        stage=stage,
        label=label,
        status=COMPLETED if completed else PENDING,
        completed_at=_ts(completed_at),
        summary=summary,
    )


@router.get("/api/v1/certificates/{certificate_id}/pipeline",
            response_model=PipelineStatusResponse)
async def get_pipeline_status(
    certificate_id: str,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns per-stage verification pipeline status for a certificate."""
    cert = await get_owned_certificate(certificate_id, user, db)

    # Fetch all related rows in parallel-ish (sequential but cheap)
    doc_type = (await db.execute(
        select(DocumentType).where(DocumentType.certificate_id == cert.id).order_by(DocumentType.id.desc())
    )).scalars().first()

    ocr = (await db.execute(
        select(OCRData).where(OCRData.certificate_id == cert.id).order_by(OCRData.id.desc())
    )).scalars().first()

    comparison = None
    if cert.group_id:
        comparison_res = await db.execute(
            select(DocumentComparison).where(DocumentComparison.group_id == cert.group_id).order_by(DocumentComparison.id.desc())
        )
        comparison = comparison_res.scalars().first()

    vr = (await db.execute(
        select(VerificationResult).where(VerificationResult.certificate_id == cert.id).order_by(VerificationResult.id.desc())
    )).scalars().first()

    fraud = (await db.execute(
        select(FraudAnalysis).where(FraudAnalysis.certificate_id == cert.id).order_by(FraudAnalysis.id.desc())
    )).scalars().first()

    trust = (await db.execute(
        select(TrustScore).where(TrustScore.certificate_id == cert.id).order_by(TrustScore.id.desc())
    )).scalars().first()

    prediction = (await db.execute(
        select(FinalPrediction).where(FinalPrediction.certificate_id == cert.id).order_by(FinalPrediction.id.desc())
    )).scalars().first()

    report = (await db.execute(
        select(VerificationReport).where(VerificationReport.certificate_id == cert.id).order_by(VerificationReport.id.desc())
    )).scalars().first()

    # ── Build pipeline stages ────────────────────────────────────────────────
    stages: list[PipelineStage] = []

    # 1. Upload
    stages.append(_stage(
        "upload", "Certificate Upload", True,
        cert.uploaded_at,
        f"{cert.file_type.upper()} — {cert.original_filename}",
    ))

    # 2. OCR
    ocr_done = ocr is not None
    stages.append(_stage(
        "ocr", "OCR Extraction", ocr_done,
        ocr.created_at if ocr else None,
        f"Accuracy: {round(ocr.ocr_accuracy * 100, 1)}% | Text: {len((ocr.raw_text or '').strip())} chars"
        if ocr and ocr.ocr_accuracy else ("Completed" if ocr_done else None),
    ))

    # 3. Document Classification
    cls_done = doc_type is not None or (ocr is not None and ocr.field_confidences and bool(ocr.field_confidences.get("_doc_type")))
    dt_name = None
    if doc_type:
        dt_val = doc_type.predicted_type.value if hasattr(doc_type.predicted_type, 'value') else str(doc_type.predicted_type)
        dt_name = f"{dt_val.replace('_', ' ').title()} — {round(doc_type.confidence_score * 100, 0):.0f}% confidence"
    elif ocr and ocr.field_confidences and ocr.field_confidences.get("_doc_type"):
        dt_val = str(ocr.field_confidences.get("_doc_type"))
        dt_name = f"{dt_val.replace('_', ' ').title()} — OCR Classified"
    stages.append(_stage(
        "classification", "Document Classification", cls_done,
        doc_type.created_at if doc_type else (ocr.created_at if ocr else None),
        dt_name if cls_done else None,
    ))

    # 4. Field Extraction
    field_count = sum([
        bool(getattr(ocr, f, None))
        for f in ["student_name", "university_name", "register_number", "roll_number",
                  "certificate_number", "date_of_birth", "graduation_year", "course", "department"]
    ]) if ocr else 0
    field_done = ocr_done and (field_count > 0 or len((ocr.raw_text or '').strip()) > 10)
    stages.append(_stage(
        "field_extraction", "Field Extraction", field_done,
        ocr.created_at if ocr else None,
        f"{field_count}/9 key fields extracted" if field_done else None,
    ))

    # 5. Comparison (optional — only meaningful for grouped certs)
    comp_done = comparison is not None
    stages.append(PipelineStage(
        stage="comparison",
        label="Document Comparison",
        status=COMPLETED if comp_done else UNAVAILABLE,
        completed_at=_ts(comparison.created_at if comparison else None),
        summary=f"Consistency: {round(comparison.consistency_percentage, 1)}%" if comp_done and comparison.consistency_percentage is not None else ("Completed" if comp_done else "Not applicable for single document"),
    ))

    # 6. QR Verification
    qr_done = vr is not None and (
        vr.qr_present is not None or vr.qr_decoded_data is not None or vr.qr_valid is not None or vr.cross_validation_status is not None
    )
    qr_summary = None
    qr_status = PENDING
    if qr_done and vr:
        if vr.qr_present is False:
            qr_status = "NOT_APPLICABLE"
            qr_summary = vr.qr_warning or "No QR Code Detected — Not Applicable"
        elif vr.qr_valid is True:
            decoded = vr.qr_decoded_data if isinstance(vr.qr_decoded_data, dict) else {}
            cert_no = decoded.get("certificate_id") or decoded.get("certificate_number") or decoded.get("register_number")
            qr_type = decoded.get("_qr_type", "detected")
            qr_summary = f"QR Valid ✓ ({qr_type}){f' [{cert_no}]' if cert_no else ''}"
            qr_status = COMPLETED
        elif vr.qr_valid is False:
            qr_status = FAILED
            qr_summary = f"QR Invalid ✗{f' ({vr.qr_warning})' if vr.qr_warning else ''}"
        else:
            qr_status = COMPLETED
            qr_summary = "QR Present (Unverified)"

    stages.append(PipelineStage(
        stage="qr_verification",
        label="QR Verification",
        status=qr_status,
        completed_at=_ts(vr.created_at if vr and qr_done else None),
        summary=qr_summary,
    ))

    # 7. SHA-256 / Hash Integrity
    hash_done = (vr is not None and vr.hash_match_status is not None) or bool(cert.sha256_hash)
    hash_summary = None
    if vr and vr.hash_match_status:
        hash_summary = f"Integrity Verified ({vr.hash_match_status})"
    elif cert.sha256_hash:
        hash_summary = f"Hash: {cert.sha256_hash[:16]}... (MATCH)"
    stages.append(_stage(
        "hash_check", "SHA-256 Hash Integrity", hash_done,
        vr.created_at if vr else (cert.uploaded_at if cert else None),
        hash_summary,
    ))

    # 8. Blockchain Verification
    bc_done = vr is not None and vr.blockchain_status is not None
    bc_summary = None
    bc_status = PENDING
    if bc_done and vr and vr.blockchain_status:
        b_status_upper = vr.blockchain_status.upper()
        if "NOT_APPLICABLE" in b_status_upper or "UNAVAILABLE" in b_status_upper:
            bc_status = "NOT_APPLICABLE"
            bc_summary = "Blockchain Not Configured"
        elif "UNREACHABLE" in b_status_upper:
            bc_status = FAILED
            bc_summary = "RPC Unreachable"
        elif "MISMATCH" in b_status_upper:
            bc_status = FAILED
            bc_summary = "Hash Mismatch ✗"
        elif "NOT_REGISTERED" in b_status_upper:
            bc_status = COMPLETED
            bc_summary = "Not Registered (Neutral)"
        elif "SKIPPED" in b_status_upper:
            bc_status = "SKIPPED"
            bc_summary = "Skipped"
        else:
            tx = f" (Tx: {vr.blockchain_tx_hash[:10]}...)" if vr.blockchain_tx_hash else ""
            bc_status = COMPLETED
            bc_summary = f"Verified: {vr.blockchain_status}{tx}"
    elif getattr(settings, "BLOCKCHAIN_PROVIDER", "none").lower() == "none":
        bc_status = "NOT_APPLICABLE"
        bc_summary = "Blockchain Not Configured"

    stages.append(PipelineStage(
        stage="blockchain",
        label="Blockchain Verification",
        status=bc_status,
        completed_at=_ts(vr.created_at if vr and bc_done else None),
        summary=bc_summary,
    ))

    # 9. Tampering Detection
    tamp_done = vr is not None and vr.tampering_score is not None
    tamp_summary = None
    tamp_status = PENDING
    if tamp_done and vr:
        if vr.tampering_risk_level == "SKIPPED":
            tamp_status = "SKIPPED"
            tamp_summary = "Skipped"
        else:
            risk = (vr.tampering_risk_level or "LOW").replace("_", " ").title()
            tamp_summary = f"{risk} — Score: {vr.tampering_score:.0f}/100"
            tamp_status = COMPLETED

    stages.append(PipelineStage(
        stage="tampering",
        label="Tampering & Forgery Detection",
        status=tamp_status,
        completed_at=_ts(vr.created_at if vr else None),
        summary=tamp_summary,
    ))

    # 10. Duplicate Detection
    dup_done = vr is not None and (
        vr.duplicate_detail is not None or vr.duplicate_match_reason is not None or vr.is_duplicate is not None
    )
    dup_summary = None
    if dup_done and vr:
        if vr.is_duplicate:
            dup_summary = f"Duplicate Detected ⚠ ({vr.duplicate_match_reason or 'Matched database record'})"
        else:
            dup_summary = "No Duplicate Found ✓"
    stages.append(_stage(
        "duplicate", "Duplicate Detection", dup_done,
        vr.created_at if vr else None,
        dup_summary,
    ))

    # 11. AI Fraud Analysis
    fraud_done = fraud is not None
    stages.append(_stage(
        "fraud_analysis", "AI Fraud Analysis", fraud_done,
        fraud.created_at if fraud else None,
        f"Fraud Probability: {round(fraud.fraud_probability * 100, 1)}%"
        if fraud and fraud.fraud_probability is not None else ("Completed" if fraud_done else None),
    ))

    # 12. Trust Score
    trust_done = trust is not None
    stages.append(_stage(
        "trust_score", "Trust Score", trust_done,
        trust.created_at if trust else None,
        f"Score: {round(trust.score, 1)}/100" if trust_done else None,
    ))

    # 13. Final Prediction
    pred_done = prediction is not None
    label_str = str(prediction.label.value if hasattr(prediction.label, "value") else prediction.label) if prediction else ""
    stages.append(_stage(
        "prediction", "Final Prediction", pred_done,
        prediction.created_at if prediction else None,
        f"{label_str.upper()} — {round(prediction.confidence_score * 100, 1)}% confidence"
        if pred_done else None,
    ))

    # 14. Report Generation
    report_done = report is not None
    stages.append(_stage(
        "report", "PDF Report Generation", report_done,
        report.generated_at if report else None,
        f"Report ID: {report.verification_id}" if report_done else None,
    ))

    # ── Overall status calculation ───────────────────────────────────────────
    completed_count = sum(1 for s in stages if s.status in (COMPLETED, "SKIPPED"))
    # Exclude UNAVAILABLE (comparison/blockchain) from denominator
    applicable = [s for s in stages if s.status != UNAVAILABLE]
    total_applicable = len(applicable)
    comp_pct = round(completed_count / total_applicable * 100, 1) if total_applicable else 0.0

    if comp_pct == 100.0:
        overall = "FULLY_COMPLETE"
    elif comp_pct == 0.0:
        overall = "NOT_STARTED"
    else:
        overall = "PARTIALLY_COMPLETE"

    return PipelineStatusResponse(
        certificate_id=cert.id,
        filename=cert.original_filename,
        file_type=cert.file_type,
        uploaded_at=_ts(cert.uploaded_at),
        overall_status=overall,
        completion_pct=comp_pct,
        stages=stages,
    )


@router.post("/api/v1/certificates/{certificate_id}/run-pipeline",
             response_model=PipelineStatusResponse,
             status_code=status.HTTP_202_ACCEPTED)
async def run_entire_pipeline(
    certificate_id: str,
    sync: bool = Query(default=False, description="Run pipeline synchronously (useful for test suites)"),
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Executes the verification pipeline asynchronously (or synchronously if sync=True).
    Returns HTTP 202 Accepted with job_id immediately so HTTP connections / Next proxy never hang up.
    Prevents concurrent runs on the same certificate, returning 409 Conflict if already in progress.
    """
    import logging
    logger = logging.getLogger("certiverify.pipeline")

    from app.models.models import VerificationJob, JobStatus, PipelineStage as JobPipelineStage
    from app.services.job_runner import enqueue_verification_job, execute_verification_pipeline

    cert = await get_owned_certificate(certificate_id, user, db)

    # Check for active job running on this certificate
    job_q = await db.execute(
        select(VerificationJob)
        .where(
            VerificationJob.certificate_id == cert.id,
            VerificationJob.status.in_([JobStatus.PROCESSING, JobStatus.QUEUED, "PROCESSING", "QUEUED"]),
        )
        .order_by(VerificationJob.created_at.desc(), VerificationJob.id.desc())
    )
    latest_job = job_q.scalars().first()

    stale_timeout = getattr(settings, "JOB_STALE_TIMEOUT_SECONDS", 120)
    now_utc = datetime.utcnow()

    if latest_job and latest_job.status in (JobStatus.PROCESSING, JobStatus.QUEUED):
        ref_time = latest_job.started_at or latest_job.created_at
        is_stale = False
        if ref_time:
            ref_naive = ref_time.replace(tzinfo=None) if hasattr(ref_time, "tzinfo") and ref_time.tzinfo else ref_time
            if (now_utc - ref_naive).total_seconds() > stale_timeout:
                is_stale = True

        if not is_stale:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A verification pipeline is already in progress for this certificate (job {latest_job.id}). Please wait for it to complete.",
            )
        else:
            logger.warning("Found stale job %s for cert %s (older than %ds). Recovering and marking FAILED.", latest_job.id, cert.id, stale_timeout)
            latest_job.status = JobStatus.FAILED
            latest_job.error_details = f"Stale job recovered after {stale_timeout}s timeout"
            await db.commit()

    # Create a fresh clean VerificationJob
    new_job = VerificationJob(
        organization_id=cert.organization_id or user.organization_id,
        certificate_id=cert.id,
        status=JobStatus.QUEUED,
        current_stage=JobPipelineStage.QUEUED,
        progress_percentage=0,
        stage_states={},
    )
    db.add(new_job)
    await db.commit()
    await db.refresh(new_job)

    if sync:
        await execute_verification_pipeline(new_job.id)
        status_resp = await get_pipeline_status(certificate_id=cert.id, user=user, db=db)
        status_resp.job_id = new_job.id
        return status_resp

    enqueue_verification_job(new_job.id)
    status_resp = await get_pipeline_status(certificate_id=cert.id, user=user, db=db)
    status_resp.job_id = new_job.id
    status_resp.overall_status = "PROCESSING"
    return status_resp

