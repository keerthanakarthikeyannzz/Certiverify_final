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

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.models import (
    Certificate, DocumentComparison, DocumentType, FinalPrediction,
    FraudAnalysis, OCRData, TrustScore, User, VerificationReport,
    VerificationResult,
)
from app.api.deps import get_current_verified_user

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
    overall_status: str             # FULLY_COMPLETE | PARTIALLY_COMPLETE | NOT_STARTED
    completion_pct: float           # 0-100
    stages: list[PipelineStage]


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
    # Ownership check
    cert_result = await db.execute(
        select(Certificate).where(
            Certificate.id == certificate_id,
            Certificate.owner_id == user.id,
        )
    )
    cert = cert_result.scalar_one_or_none()
    if cert is None:
        raise HTTPException(status_code=404, detail="Certificate not found.")

    # Fetch all related rows in parallel-ish (sequential but cheap)
    doc_type = (await db.execute(
        select(DocumentType).where(DocumentType.certificate_id == certificate_id).order_by(DocumentType.id.desc())
    )).scalars().first()

    ocr = (await db.execute(
        select(OCRData).where(OCRData.certificate_id == certificate_id).order_by(OCRData.id.desc())
    )).scalars().first()

    comparison = None
    if cert.group_id:
        comparison_res = await db.execute(
            select(DocumentComparison).where(DocumentComparison.group_id == cert.group_id).order_by(DocumentComparison.id.desc())
        )
        comparison = comparison_res.scalars().first()

    vr = (await db.execute(
        select(VerificationResult).where(VerificationResult.certificate_id == certificate_id).order_by(VerificationResult.id.desc())
    )).scalars().first()

    fraud = (await db.execute(
        select(FraudAnalysis).where(FraudAnalysis.certificate_id == certificate_id).order_by(FraudAnalysis.id.desc())
    )).scalars().first()

    trust = (await db.execute(
        select(TrustScore).where(TrustScore.certificate_id == certificate_id).order_by(TrustScore.id.desc())
    )).scalars().first()

    prediction = (await db.execute(
        select(FinalPrediction).where(FinalPrediction.certificate_id == certificate_id).order_by(FinalPrediction.id.desc())
    )).scalars().first()

    report = (await db.execute(
        select(VerificationReport).where(VerificationReport.certificate_id == certificate_id).order_by(VerificationReport.id.desc())
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
    if qr_done:
        if vr.qr_valid is True:
            decoded = vr.qr_decoded_data if isinstance(vr.qr_decoded_data, dict) else {}
            cert_no = decoded.get("certificate_id") or decoded.get("certificate_number") or decoded.get("register_number")
            qr_summary = f"QR Valid ✓{f' ({cert_no})' if cert_no else ''}"
        elif vr.qr_present and vr.qr_valid is False:
            qr_summary = "QR Invalid ✗"
        elif vr.qr_present:
            qr_summary = "QR Present (Unverified)"
        else:
            qr_summary = "No QR Code Detected ✓"
    stages.append(_stage(
        "qr_verification", "QR Verification", qr_done,
        vr.created_at if vr else None,
        qr_summary,
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
    if bc_done and vr:
        if vr.blockchain_status == "skipped" or (vr.qr_present is True and vr.qr_valid is True):
            bc_status = "SKIPPED"
            bc_summary = "Skipped — Verified via QR"
        elif vr.blockchain_status == "unavailable":
            bc_status = UNAVAILABLE
            bc_summary = "Unavailable"
        elif vr.blockchain_status == "error":
            bc_status = FAILED
            bc_summary = "Error"
        else:
            status_txt = vr.blockchain_status.replace("_", " ").title()
            tx = f" (Tx: {vr.blockchain_tx_hash[:12]}...)" if vr.blockchain_tx_hash else ""
            bc_summary = f"{status_txt}{tx}"
            bc_status = COMPLETED
    elif vr and vr.qr_present is True and vr.qr_valid is True:
        bc_status = "SKIPPED"
        bc_summary = "Skipped — Verified via QR"

    stages.append(PipelineStage(
        stage="blockchain",
        label="Blockchain Verification",
        status=bc_status,
        completed_at=_ts(vr.created_at if vr else None),
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
             response_model=PipelineStatusResponse)
async def run_entire_pipeline(
    certificate_id: str,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Executes the sequential verification pipeline end-to-end:
    Upload -> OCR -> QR Detection -> QR Verification ->
    If QR Verified -> Genuine / Skip Blockchain & Tampering -> Trust Score
    If QR Not Verified -> Blockchain -> Tampering -> Trust Score -> Final Classification
    """
    import logging
    logger = logging.getLogger("certiverify.pipeline")

    from app.api.ocr import extract_ocr
    from app.api.document_type import classify_certificate
    from app.api.verification import (
        run_qr_check, run_blockchain_verification, run_tampering_detection, run_duplicate_detection
    )
    from app.api.fraud import run_fraud_analysis
    from app.api.trust_score import run_trust_score
    from app.api.prediction import run_prediction
    from app.api.report import generate_report

    cert_result = await db.execute(
        select(Certificate).where(
            Certificate.id == certificate_id,
            Certificate.owner_id == user.id,
        )
    )
    cert = cert_result.scalar_one_or_none()
    if cert is None:
        raise HTTPException(status_code=404, detail="Certificate not found.")

    # 1. OCR Extraction (Must execute first)
    try:
        await extract_ocr(certificate_id=cert.id, user=user, db=db)
    except Exception as exc:
        logger.exception("Pipeline OCR extraction failed for cert %s: %s", cert.id, exc)
        return await get_pipeline_status(certificate_id=cert.id, user=user, db=db)

    # 2. Document Classification
    try:
        await classify_certificate(certificate_id=cert.id, user=user, db=db)
    except Exception as exc:
        logger.exception("Pipeline Document classification failed for cert %s: %s", cert.id, exc)

    # 3. QR Detection & Verification
    vr_row = None
    try:
        vr_row = await run_qr_check(certificate_id=cert.id, user=user, db=db)
    except Exception as exc:
        logger.exception("Pipeline QR check failed for cert %s: %s", cert.id, exc)

    qr_verified = vr_row is not None and vr_row.qr_present is True and vr_row.qr_valid is True

    # 4. Success Path vs Fallback Path
    if qr_verified:
        logger.info("QR code verified for cert %s. Skipping Blockchain check.", cert.id)
        vr_row.blockchain_status = "skipped"
        await db.commit()
    else:
        # Fallback Path: Execute Blockchain check
        try:
            await run_blockchain_verification(certificate_id=cert.id, user=user, db=db)
        except Exception as exc:
            logger.exception("Pipeline Blockchain verification failed for cert %s: %s", cert.id, exc)

    try:
        await run_tampering_detection(certificate_id=cert.id, user=user, db=db)
    except Exception as exc:
        logger.exception("Pipeline Tampering detection failed for cert %s: %s", cert.id, exc)

    # 5. Duplicate Detection
    try:
        await run_duplicate_detection(certificate_id=cert.id, user=user, db=db)
    except Exception as exc:
        logger.exception("Pipeline Duplicate detection failed for cert %s: %s", cert.id, exc)

    # 6. Fraud Analysis & Trust Score
    try:
        await run_fraud_analysis(certificate_id=cert.id, user=user, db=db)
    except Exception as exc:
        logger.exception("Pipeline Fraud analysis failed for cert %s: %s", cert.id, exc)

    try:
        await run_trust_score(certificate_id=cert.id, user=user, db=db)
    except Exception as exc:
        logger.exception("Pipeline Trust score failed for cert %s: %s", cert.id, exc)

    # 7. Final Prediction
    try:
        await run_prediction(certificate_id=cert.id, user=user, db=db)
    except Exception as exc:
        logger.exception("Pipeline Prediction failed for cert %s: %s", cert.id, exc)

    # 8. Report Generation
    try:
        await generate_report(certificate_id=cert.id, user=user, db=db)
    except Exception as exc:
        logger.exception("Pipeline Report generation failed for cert %s: %s", cert.id, exc)

    return await get_pipeline_status(certificate_id=cert.id, user=user, db=db)

