"""
MODULE 10 - VERIFICATION REPORT & DASHBOARD API

Endpoints:
  POST   /api/v1/certificates/{certificate_id}/generate-report  → generate PDF, persist VerificationReport
  GET    /api/v1/certificates/{certificate_id}/report           → report metadata
  GET    /api/v1/certificates/{certificate_id}/download-report  → stream the saved PDF
  GET    /api/v1/dashboard/stats                                → dashboard aggregate stats
"""
import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.models import (
    Certificate, DocumentComparison, DocumentType, FinalPrediction,
    FraudAnalysis, OCRData, TrustScore, User, VerificationReport,
    VerificationResult,
)
from app.schemas.report_schemas import (
    DashboardStatsResponse,
    PredictionDistribution,
    RecentCertificate,
    TimelineEvent,
    VerificationReportResponse,
)
from app.services.report_service import compute_digital_signature, generate_report_pdf
from app.core.config import settings
from app.api.deps import get_current_verified_user

router = APIRouter(tags=["Verification Report"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_verification_id() -> str:
    """Human-readable ID: CV-2026-XXXXXXXX"""
    year = datetime.utcnow().year
    unique = uuid.uuid4().hex[:8].upper()
    return f"CV-{year}-{unique}"


async def _fetch_one(db: AsyncSession, model, condition):
    result = await db.execute(select(model).where(condition))
    return result.scalar_one_or_none()


def _row_to_dict(row) -> dict:
    if row is None:
        return None
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


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
    Aggregates all module data, generates a PDF, persists it, and returns report metadata.
    """
    cert = await _get_owned_certificate(certificate_id, user, db)

    # Fetch all module data
    doc_type_row = await _fetch_one(db, DocumentType, DocumentType.certificate_id == cert.id)
    ocr_row = await _fetch_one(db, OCRData, OCRData.certificate_id == cert.id)
    verification_row = await _fetch_one(db, VerificationResult, VerificationResult.certificate_id == cert.id)
    fraud_row = await _fetch_one(db, FraudAnalysis, FraudAnalysis.certificate_id == cert.id)
    trust_row = await _fetch_one(db, TrustScore, TrustScore.certificate_id == cert.id)
    prediction_row = await _fetch_one(db, FinalPrediction, FinalPrediction.certificate_id == cert.id)

    comparison_row = None
    if cert.group_id:
        comparison_row = await _fetch_one(db, DocumentComparison, DocumentComparison.group_id == cert.group_id)

    # Require completed processing before generating report
    if not verification_row or not prediction_row:
        raise HTTPException(
            status_code=400,
            detail="Cannot generate report while required processing is pending. Please execute the verification pipeline first."
        )

    # Determine verification ID (reuse if report exists)
    existing_report = await _fetch_one(db, VerificationReport, VerificationReport.certificate_id == cert.id)
    verification_id = existing_report.verification_id if existing_report else _make_verification_id()
    generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # Build dicts for the PDF service
    cert_dict = _row_to_dict(cert)
    cert_dict["uploaded_at"] = cert.uploaded_at.strftime("%Y-%m-%d %H:%M UTC")

    report_meta = {
        "verification_id": verification_id,
        "generated_at": generated_at,
        "digital_signature": None,  # computed below
    }

    # Compute digital signature before PDF (it's embedded in the PDF)
    sig = compute_digital_signature(cert_dict, report_meta)
    report_meta["digital_signature"] = sig

    # Generate PDF bytes
    pdf_bytes = generate_report_pdf(
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

    # Persist PDF to disk (using the configured upload dir)
    reports_dir = os.path.join(settings.UPLOAD_DIR, "reports")
    os.makedirs(reports_dir, exist_ok=True)
    pdf_filename = f"{verification_id}.pdf"
    pdf_path = os.path.join(reports_dir, pdf_filename)
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    # Upsert VerificationReport
    if existing_report is None:
        report_row = VerificationReport(
            certificate_id=cert.id,
            verification_id=verification_id,
            pdf_path=pdf_path,
            digital_signature=sig,
        )
        db.add(report_row)
    else:
        existing_report.pdf_path = pdf_path
        existing_report.digital_signature = sig
        existing_report.generated_at = datetime.utcnow()
        report_row = existing_report

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
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Streams the saved PDF file."""
    cert = await _get_owned_certificate(certificate_id, user, db)
    report_row = await _fetch_one(db, VerificationReport, VerificationReport.certificate_id == cert.id)
    if not report_row or not report_row.pdf_path:
        raise HTTPException(
            status_code=404,
            detail="PDF not found. Generate the report first via POST /generate-report.",
        )
    if not os.path.exists(report_row.pdf_path):
        raise HTTPException(
            status_code=404,
            detail="PDF file is missing from storage. Please regenerate the report.",
        )

    def _iter_file(path: str):
        with open(path, "rb") as f:
            yield from f

    filename = f"CertiVerify_{report_row.verification_id}.pdf"
    return StreamingResponse(
        _iter_file(report_row.pdf_path),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
    # Priority 8 — additional bulk fetches
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

    # Priority 8 — 5 new aggregate fields
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
        # Priority 8
        duplicate_count=duplicate_count,
        tampered_count=tampered_count,
        qr_verified_count=qr_verified_count,
        blockchain_verified_count=blockchain_verified_count,
        doc_type_distribution=doc_type_dist,
    )
