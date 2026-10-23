"""
MODULE 8 - VERIFICATION REPORT & DASHBOARD API

Endpoints:
  POST   /api/v1/certificates/{certificate_id}/generate-report  → generate PDF, persist VerificationReport
  GET    /api/v1/certificates/{certificate_id}/report           → report metadata
  GET    /api/v1/certificates/{certificate_id}/download-report  → stream the saved PDF (scoped auth)
  POST   /api/v1/certificates/{certificate_id}/verify-signature → verify HMAC-SHA256 signature
  GET    /api/v1/reports                                        → list all generated reports
  GET    /api/v1/dashboard/stats                                → dashboard aggregate stats
"""
import asyncio
import logging
import os
import re
import urllib.parse
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_verified_user,
    get_current_verified_user_flexible,
    get_owned_certificate,
    normalize_cert_id,
)
from app.core.config import settings
from app.db.database import get_db
from app.models.models import (
    Certificate, DocumentComparison, DocumentType, FinalPrediction,
    FraudAnalysis, OCRData, Organization, TrustScore, User, UserRole,
    VerificationJob, VerificationReport, VerificationResult,
)
from app.schemas.report_schemas import (
    DashboardStatsResponse,
    PredictionDistribution,
    RecentCertificate,
    ReportListItem,
    SignatureVerificationResponse,
    TimelineEvent,
    VerificationReportResponse,
)
from app.services.audit_service import log_audit_event
from app.services.report_service import (
    compute_report_signature,
    generate_report_pdf,
    get_report_output_dir,
    make_verification_id,
    resolve_report_path,
    verify_report_signature,
)

logger = logging.getLogger("certiverify.report_api")

router = APIRouter(tags=["Verification Report"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _fetch_one(db: AsyncSession, model, condition):
    result = await db.execute(select(model).where(condition).order_by(model.id.desc()))
    return result.scalars().first()


def _row_to_dict(row) -> dict | None:
    if row is None:
        return None
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


async def _get_owned_certificate(certificate_id: str, user: User, db: AsyncSession) -> Certificate:
    from app.api.deps import get_owned_certificate
    return await get_owned_certificate(certificate_id, user, db)


# ---------------------------------------------------------------------------
# POST /api/v1/certificates/{certificate_id}/generate-report
# ---------------------------------------------------------------------------

@router.post(
    "/api/v1/certificates/{certificate_id}/generate-report",
    response_model=VerificationReportResponse,
)
@router.post(
    "/api/v1/certificates/{certificate_id}/report",
    response_model=VerificationReportResponse,
    include_in_schema=False,
)
async def generate_report(
    certificate_id: str,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Aggregates all stored results, generates an official PDF report,
    computes an HMAC-SHA256 digital signature, persists it, and returns report metadata.
    Idempotent: Re-generating safely archives previous PDFs and updates the active canonical record.
    """
    cert = await _get_owned_certificate(certificate_id, user, db)

    # Fetch stored results across all pipeline stages
    doc_type_row = await _fetch_one(db, DocumentType, DocumentType.certificate_id == cert.id)
    ocr_row = await _fetch_one(db, OCRData, OCRData.certificate_id == cert.id)
    verification_row = await _fetch_one(db, VerificationResult, VerificationResult.certificate_id == cert.id)
    fraud_row = await _fetch_one(db, FraudAnalysis, FraudAnalysis.certificate_id == cert.id)
    trust_row = await _fetch_one(db, TrustScore, TrustScore.certificate_id == cert.id)
    prediction_row = await _fetch_one(db, FinalPrediction, FinalPrediction.certificate_id == cert.id)

    comparison_row = None
    if cert.group_id:
        comparison_row = await _fetch_one(db, DocumentComparison, DocumentComparison.group_id == cert.group_id)

    # Require minimum verification completion before generating official report
    missing = []
    if not verification_row:
        missing.append("Verification stages (QR/Tampering/Duplicate)")
    if not prediction_row:
        missing.append("Final Prediction & Trust Score")
    if not ocr_row:
        missing.append("OCR extraction")
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot generate report while required processing is pending. Missing: {', '.join(missing)}. Please execute the verification pipeline first."
        )

    # Fetch auditing organization branding
    org_name = getattr(settings, "REPORT_ORG_NAME", "CertiVerify Enterprise")
    if cert.organization_id:
        org_res = await db.execute(select(Organization).where(Organization.id == cert.organization_id))
        org_obj = org_res.scalar_one_or_none()
        if org_obj and org_obj.name:
            org_name = org_obj.name

    # Check for existing report (Idempotent re-generation)
    existing_report = await _fetch_one(db, VerificationReport, VerificationReport.certificate_id == cert.id)
    verification_id = make_verification_id()
    generated_at_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # If an existing PDF exists, archive it in the filesystem archive directory
    out_dir = get_report_output_dir()
    existing_resolved = resolve_report_path(existing_report.pdf_path if existing_report else None)
    if existing_report and existing_resolved and existing_resolved.is_file():
        archive_dir = out_dir / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        old_ts = int(existing_report.generated_at.timestamp()) if existing_report.generated_at else int(datetime.utcnow().timestamp())
        archive_filename = f"{existing_report.verification_id}_archived_{old_ts}.pdf"
        archive_path = archive_dir / archive_filename
        try:
            os.replace(str(existing_resolved), str(archive_path))
            logger.info("Archived previous report PDF to %s", archive_path)
        except Exception as exc:
            logger.warning("Could not archive previous report PDF: %s", exc)

    # Build dictionaries for PDF generation
    cert_dict = _row_to_dict(cert)
    cert_dict["uploaded_at"] = cert.uploaded_at.strftime("%Y-%m-%d %H:%M UTC") if cert.uploaded_at else "—"

    report_meta = {
        "verification_id": verification_id,
        "generated_at": generated_at_str,
        "verifier_name": user.full_name or "Authorized Verifier",
        "verifier_email": user.email or "verifier@certiverify.ai",
        "organization_name": org_name,
        "digital_signature": None,
    }

    # Generate PDF bytes strictly from stored results (offloaded to thread to keep event loop responsive)
    try:
        pdf_bytes = await asyncio.to_thread(
            generate_report_pdf,
            cert=cert_dict,
            doc_type_row=_row_to_dict(doc_type_row),
            ocr_row=_row_to_dict(ocr_row),
            comparison_row=_row_to_dict(comparison_row),
            verification_row=_row_to_dict(verification_row),
            fraud_row=_row_to_dict(fraud_row),
            trust_row=_row_to_dict(trust_row),
            prediction_row=_row_to_dict(prediction_row),
            report_row=report_meta,
        )
    except Exception as exc:
        logger.exception("Failed to build PDF report for certificate %s: %s", cert.id, exc)
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(exc)}")

    # Compute detached digital signature over the generated PDF bytes
    try:
        sig = compute_report_signature(pdf_bytes)
        report_meta["digital_signature"] = sig
    except RuntimeError as re_err:
        raise HTTPException(status_code=500, detail=str(re_err))

    # Persist PDF to canonical reports storage directory atomically
    pdf_filename = f"{verification_id}.pdf"
    pdf_file_path = out_dir / pdf_filename
    tmp_file_path = out_dir / f"{verification_id}.tmp"
    with open(tmp_file_path, "wb") as f:
        f.write(pdf_bytes)
    os.replace(str(tmp_file_path), str(pdf_file_path))
    pdf_path = str(pdf_file_path)

    # Upsert VerificationReport row
    is_new = existing_report is None
    if is_new:
        report_row = VerificationReport(
            certificate_id=cert.id,
            verification_id=verification_id,
            pdf_path=pdf_path,
            digital_signature=sig,
            generated_at=datetime.utcnow(),
        )
        db.add(report_row)
    else:
        existing_report.verification_id = verification_id
        existing_report.pdf_path = pdf_path
        existing_report.digital_signature = sig
        existing_report.generated_at = datetime.utcnow()
        report_row = existing_report

    # Update VerificationJob stage_states if one exists
    try:
        job_res = await db.execute(
            select(VerificationJob)
            .where(VerificationJob.certificate_id == cert.id)
            .order_by(VerificationJob.id.desc())
        )
        job = job_res.scalars().first()
        if job:
            s_states = dict(job.stage_states or {})
            s_states["report"] = {
                "status": "COMPLETED",
                "verification_id": verification_id,
                "pdf_path": pdf_path,
                "digital_signature": sig,
                "completed_at": datetime.utcnow().isoformat(),
            }
            job.stage_states = s_states
    except Exception as job_err:
        logger.warning("Could not update VerificationJob stage_states for report: %s", job_err)

    # Audit logging
    await log_audit_event(
        db,
        action="verification:report_generated" if is_new else "verification:report_regenerated",
        entity_type="verification_report",
        actor_user_id=user.id,
        organization_id=cert.organization_id or user.organization_id,
        entity_id=cert.id,
        metadata_json={
            "certificate_id": cert.id,
            "verification_id": verification_id,
            "digital_signature": sig,
            "pdf_path": pdf_path,
        },
    )

    await db.commit()
    await db.refresh(report_row)
    return report_row


# ---------------------------------------------------------------------------
# GET /api/v1/certificates/{certificate_id}/report
# ---------------------------------------------------------------------------

@router.get(
    "/api/v1/certificates/{certificate_id}/report",
    response_model=VerificationReportResponse,
)
async def get_report(
    certificate_id: str,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    cert = await _get_owned_certificate(certificate_id, user, db)
    report_row = await _fetch_one(db, VerificationReport, VerificationReport.certificate_id == cert.id)
    if not report_row:
        raise HTTPException(
            status_code=404,
            detail="No report has been generated for this certificate yet. Call POST /generate-report first.",
        )
    return report_row


# ---------------------------------------------------------------------------
# GET /api/v1/certificates/{certificate_id}/download-report
# ---------------------------------------------------------------------------

@router.get("/api/v1/certificates/{certificate_id}/download-report")
async def download_report(
    certificate_id: str,
    inline: bool = Query(False, description="Open PDF inline instead of attachment"),
    user: User = Depends(get_current_verified_user_flexible),
    db: AsyncSession = Depends(get_db),
):
    """
    Streams the saved PDF report using FileResponse with RFC 5987 headers.
    Scoped by organization_id and owner.
    Supports Bearer token headers and ?token= query parameter for direct browser downloads/views.
    If the report row exists in the database but the file on disk is missing,
    automatically re-generates the report PDF from stored pipeline stage results.
    """
    try:
        cert = await _get_owned_certificate(certificate_id, user, db)
    except HTTPException:
        raise
    except Exception as auth_err:
        logger.exception("Authorization error accessing certificate %s: %s", certificate_id, auth_err)
        raise HTTPException(status_code=403, detail="Not authorized to access this certificate's report.")

    report_row = await _fetch_one(db, VerificationReport, VerificationReport.certificate_id == cert.id)
    if not report_row:
        raise HTTPException(
            status_code=404,
            detail="Verification report not found for this certificate. Please generate the report first via POST /generate-report.",
        )

    resolved_path = resolve_report_path(report_row.pdf_path, report_row.verification_id)

    # Self-healing: If report row exists in DB but PDF file is missing on disk, regenerate on the fly
    if not resolved_path or not resolved_path.is_file():
        logger.warning(
            "Report PDF file missing from disk for cert %s (stored: %s). Auto-regenerating...",
            cert.id, report_row.pdf_path
        )
        try:
            doc_type_row = await _fetch_one(db, DocumentType, DocumentType.certificate_id == cert.id)
            ocr_row = await _fetch_one(db, OCRData, OCRData.certificate_id == cert.id)
            verification_row = await _fetch_one(db, VerificationResult, VerificationResult.certificate_id == cert.id)
            fraud_row = await _fetch_one(db, FraudAnalysis, FraudAnalysis.certificate_id == cert.id)
            trust_row = await _fetch_one(db, TrustScore, TrustScore.certificate_id == cert.id)
            prediction_row = await _fetch_one(db, FinalPrediction, FinalPrediction.certificate_id == cert.id)
            comparison_row = None
            if cert.group_id:
                comparison_row = await _fetch_one(db, DocumentComparison, DocumentComparison.group_id == cert.group_id)

            org_name = getattr(settings, "REPORT_ORG_NAME", "CertiVerify Enterprise")
            if cert.organization_id:
                org_res = await db.execute(select(Organization).where(Organization.id == cert.organization_id))
                org_obj = org_res.scalar_one_or_none()
                if org_obj and org_obj.name:
                    org_name = org_obj.name

            cert_dict = _row_to_dict(cert)
            cert_dict["uploaded_at"] = cert.uploaded_at.strftime("%Y-%m-%d %H:%M UTC") if cert.uploaded_at else "—"

            report_meta = {
                "verification_id": report_row.verification_id,
                "generated_at": report_row.generated_at.strftime("%Y-%m-%d %H:%M UTC") if report_row.generated_at else datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
                "verifier_name": user.full_name or "Authorized Verifier",
                "verifier_email": user.email or "verifier@certiverify.ai",
                "organization_name": org_name,
                "digital_signature": report_row.digital_signature,
            }

            pdf_bytes = await asyncio.to_thread(
                generate_report_pdf,
                cert=cert_dict,
                doc_type_row=_row_to_dict(doc_type_row),
                ocr_row=_row_to_dict(ocr_row),
                comparison_row=_row_to_dict(comparison_row),
                verification_row=_row_to_dict(verification_row),
                fraud_row=_row_to_dict(fraud_row),
                trust_row=_row_to_dict(trust_row),
                prediction_row=_row_to_dict(prediction_row),
                report_row=report_meta,
            )

            sig = compute_report_signature(pdf_bytes)
            out_dir = get_report_output_dir()
            pdf_filename = f"{report_row.verification_id}.pdf"
            new_file_path = out_dir / pdf_filename
            with open(new_file_path, "wb") as f:
                f.write(pdf_bytes)

            report_row.pdf_path = str(new_file_path)
            report_row.digital_signature = sig
            await db.commit()
            await db.refresh(report_row)
            resolved_path = new_file_path
            logger.info("Successfully regenerated report PDF for cert %s at %s", cert.id, resolved_path)
        except Exception as regen_err:
            logger.exception("Failed to regenerate missing report PDF for cert %s: %s", cert.id, regen_err)
            raise HTTPException(
                status_code=404,
                detail=f"Report PDF file is missing and could not be regenerated: {str(regen_err)}",
            )

    try:
        # Determine disposition
        disposition_type = "inline" if inline else "attachment"

        # Format RFC 5987 Content-Disposition header with clean ASCII fallback
        base_name = f"CertiVerify_{report_row.verification_id}"
        if cert.original_filename:
            raw_stem = os.path.splitext(cert.original_filename)[0]
            raw_filename = f"CertiVerify_{raw_stem}_{report_row.verification_id}.pdf"
        else:
            raw_filename = f"{base_name}.pdf"

        # ASCII-only fallback (only alphanumeric, dash, underscore, dot)
        ascii_clean = re.sub(r'[^a-zA-Z0-9_\-.]', '_', raw_filename)
        if not ascii_clean.endswith(".pdf"):
            ascii_clean += ".pdf"

        # RFC 5987 percent-encoded UTF-8 filename
        utf8_encoded = urllib.parse.quote(raw_filename, encoding="utf-8")
        content_disposition = f'{disposition_type}; filename="{ascii_clean}"; filename*=UTF-8\'\'{utf8_encoded}'

        return FileResponse(
            path=str(resolved_path),
            media_type="application/pdf",
            headers={
                "Content-Disposition": content_disposition,
                "Access-Control-Expose-Headers": "Content-Disposition, Content-Length",
            },
        )
    except Exception as exc:
        logger.exception("Failed to stream report PDF for cert %s (report %s): %s", cert.id, report_row.id, exc)
        raise HTTPException(status_code=500, detail=f"Failed to stream verification report: {str(exc)}")


# ---------------------------------------------------------------------------
# POST /api/v1/certificates/{certificate_id}/verify-signature
# ---------------------------------------------------------------------------

@router.post(
    "/api/v1/certificates/{certificate_id}/verify-signature",
    response_model=SignatureVerificationResponse,
)
async def verify_signature(
    certificate_id: str,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Verifies the cryptographic HMAC-SHA256 digital signature of the PDF report on disk.
    Detects any tampering or byte alterations to the report document.
    """
    cert = await _get_owned_certificate(certificate_id, user, db)
    report_row = await _fetch_one(db, VerificationReport, VerificationReport.certificate_id == cert.id)
    if not report_row or not report_row.pdf_path:
        raise HTTPException(
            status_code=404,
            detail="Verification report not found for this certificate. Generate the report first.",
        )

    resolved_path = resolve_report_path(report_row.pdf_path, report_row.verification_id)
    if not resolved_path or not resolved_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Report PDF file is missing from storage.",
        )

    is_valid = verify_report_signature(
        str(resolved_path),
        report_row.digital_signature or "",
    )

    detail_msg = (
        "Cryptographic digital signature verified: PDF document matches institutional key and has not been altered."
        if is_valid
        else "Signature verification failed: document content has been altered, corrupted, or signing key mismatch."
    )

    return SignatureVerificationResponse(
        is_valid=is_valid,
        verification_id=report_row.verification_id,
        digital_signature=report_row.digital_signature,
        checked_at=datetime.utcnow(),
        detail=detail_msg,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/reports
# ---------------------------------------------------------------------------

@router.get("/api/v1/reports", response_model=list[ReportListItem])
async def list_reports(
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lists all generated verification reports scoped to the current user's organization or ownership.
    """
    query = (
        select(VerificationReport, Certificate, FinalPrediction, TrustScore)
        .join(Certificate, VerificationReport.certificate_id == Certificate.id)
        .outerjoin(FinalPrediction, Certificate.id == FinalPrediction.certificate_id)
        .outerjoin(TrustScore, Certificate.id == TrustScore.certificate_id)
    )

    if user.role != UserRole.ADMIN:
        if user.organization_id:
            query = query.where(
                (Certificate.organization_id == user.organization_id)
                | (Certificate.owner_id == user.id)
            )
        else:
            query = query.where(Certificate.owner_id == user.id)
    elif user.organization_id:
        query = query.where(
            (Certificate.organization_id == user.organization_id)
            | (Certificate.owner_id == user.id)
        )

    query = query.order_by(VerificationReport.generated_at.desc())
    results = (await db.execute(query)).all()

    items = []
    for rep, c, pred, trust in results:
        items.append(
            ReportListItem(
                id=rep.id,
                certificate_id=c.id,
                certificate_filename=c.original_filename,
                file_type=c.file_type,
                sha256_hash=c.sha256_hash,
                verification_id=rep.verification_id,
                generated_at=rep.generated_at,
                digital_signature=rep.digital_signature,
                pdf_path=rep.pdf_path,
                prediction_label=pred.label if pred else None,
                trust_score=trust.score if trust else None,
            )
        )
    return items


# ---------------------------------------------------------------------------
# GET /api/v1/dashboard/stats
# ---------------------------------------------------------------------------

@router.get("/api/v1/dashboard/stats", response_model=DashboardStatsResponse)
async def get_dashboard_stats(
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns aggregated statistics for the current user's dashboard.
    All data is sourced from existing module tables — no mock data.
    """
    # 1. Fetch all certificates owned by the user
    certs_result = await db.execute(
        select(Certificate)
        .where(Certificate.owner_id == user.id)
        .order_by(Certificate.uploaded_at.desc())
    )
    certs = certs_result.scalars().all()
    cert_ids = [c.id for c in certs]
    total = len(certs)

    if not cert_ids:
        return DashboardStatsResponse(
            total_certificates=0,
            prediction_distribution=PredictionDistribution(),
            recent_certificates=[],
            timeline=[],
            total_reports_generated=0,
        )

    # 2. Bulk-fetch related rows
    def _map_by_cert_id(rows) -> dict:
        return {r.certificate_id: r for r in rows}

    ocr_rows = _map_by_cert_id(
        (await db.execute(select(OCRData).where(OCRData.certificate_id.in_(cert_ids)))).scalars().all()
    )
    trust_rows = _map_by_cert_id(
        (await db.execute(select(TrustScore).where(TrustScore.certificate_id.in_(cert_ids)))).scalars().all()
    )
    prediction_rows = _map_by_cert_id(
        (await db.execute(select(FinalPrediction).where(FinalPrediction.certificate_id.in_(cert_ids)))).scalars().all()
    )
    fraud_rows = _map_by_cert_id(
        (await db.execute(select(FraudAnalysis).where(FraudAnalysis.certificate_id.in_(cert_ids)))).scalars().all()
    )
    report_rows = _map_by_cert_id(
        (await db.execute(select(VerificationReport).where(VerificationReport.certificate_id.in_(cert_ids)))).scalars().all()
    )
    vr_rows_list = (await db.execute(
        select(VerificationResult).where(VerificationResult.certificate_id.in_(cert_ids))
    )).scalars().all()
    dt_rows_list = (await db.execute(
        select(DocumentType).where(DocumentType.certificate_id.in_(cert_ids))
    )).scalars().all()

    # 3. Aggregate stats
    trust_scores = [t.score for t in trust_rows.values() if t.score is not None]
    avg_trust = round(sum(trust_scores) / len(trust_scores), 2) if trust_scores else None

    ocr_accs = [o.ocr_accuracy for o in ocr_rows.values() if o.ocr_accuracy is not None]
    avg_ocr = round(sum(ocr_accs) / len(ocr_accs), 4) if ocr_accs else None

    fraud_probs = [f.fraud_probability for f in fraud_rows.values() if f.fraud_probability is not None]
    avg_fraud = round(sum(fraud_probs) / len(fraud_probs), 4) if fraud_probs else None

    duplicate_count = sum(1 for vr in vr_rows_list if vr.is_duplicate)
    tampered_count = sum(
        1 for vr in vr_rows_list
        if vr.tampering_risk_level in ("HIGH_RISK", "VERY_HIGH_RISK")
    )
    qr_verified_count = sum(1 for vr in vr_rows_list if vr.qr_valid is True)
    blockchain_verified_count = sum(
        1 for vr in vr_rows_list if vr.blockchain_status == "verified"
    )
    doc_type_dist: dict = {}
    for dt in dt_rows_list:
        key = str(dt.predicted_type.value if hasattr(dt.predicted_type, "value") else dt.predicted_type)
        doc_type_dist[key] = doc_type_dist.get(key, 0) + 1

    dist = PredictionDistribution()
    for cert in certs:
        pred = prediction_rows.get(cert.id)
        if pred:
            if pred.label == "genuine":
                dist.genuine += 1
            elif pred.label == "suspicious":
                dist.suspicious += 1
            elif pred.label == "fake":
                dist.fake += 1
            elif "inconclusive" in str(pred.label).lower():
                dist.inconclusive += 1
            else:
                dist.not_run += 1

    total_reports = len(report_rows)

    # 4. Recent certificates (last 10)
    recent: list[RecentCertificate] = []
    for cert in certs[:10]:
        trust = trust_rows.get(cert.id)
        ocr = ocr_rows.get(cert.id)
        pred = prediction_rows.get(cert.id)
        fraud = fraud_rows.get(cert.id)
        rep = report_rows.get(cert.id)
        recent.append(RecentCertificate(
            id=cert.id,
            original_filename=cert.original_filename,
            file_type=cert.file_type,
            uploaded_at=cert.uploaded_at,
            trust_score=trust.score if trust else None,
            ocr_accuracy=ocr.ocr_accuracy if ocr else None,
            prediction_label=pred.label if pred else None,
            fraud_probability=fraud.fraud_probability if fraud else None,
            has_report=rep is not None,
            verification_id=rep.verification_id if rep else None,
        ))

    # 5. Verification Timeline (last 20 events across all certificates)
    timeline: list[TimelineEvent] = []
    for cert in certs[:20]:
        timeline.append(TimelineEvent(
            certificate_id=cert.id,
            filename=cert.original_filename,
            event="uploaded",
            timestamp=cert.uploaded_at,
        ))
        if cert.id in ocr_rows:
            o = ocr_rows[cert.id]
            timeline.append(TimelineEvent(
                certificate_id=cert.id,
                filename=cert.original_filename,
                event="ocr",
                timestamp=o.created_at,
                label=f"OCR: {round(o.ocr_accuracy * 100)}%" if o.ocr_accuracy else None,
            ))
        if cert.id in prediction_rows:
            p = prediction_rows[cert.id]
            timeline.append(TimelineEvent(
                certificate_id=cert.id,
                filename=cert.original_filename,
                event="predicted",
                timestamp=p.created_at,
                label=p.label.title(),
            ))
        if cert.id in report_rows:
            r = report_rows[cert.id]
            timeline.append(TimelineEvent(
                certificate_id=cert.id,
                filename=cert.original_filename,
                event="report",
                timestamp=r.generated_at,
                label=r.verification_id,
            ))

    timeline.sort(key=lambda x: x.timestamp, reverse=True)

    return DashboardStatsResponse(
        total_certificates=total,
        avg_trust_score=avg_trust,
        prediction_distribution=dist,
        recent_certificates=recent,
        timeline=timeline[:30],
        total_reports_generated=total_reports,
        avg_ocr_accuracy=avg_ocr,
        avg_fraud_probability=avg_fraud,
        duplicate_count=duplicate_count,
        tampered_count=tampered_count,
        qr_verified_count=qr_verified_count,
        blockchain_verified_count=blockchain_verified_count,
        doc_type_distribution=doc_type_dist,
    )
