"""
MODULE 2 - CERTIFICATE UPLOAD
Multi-file upload (PDF/JPG/JPEG/PNG), drag-and-drop is a frontend concern —
this API accepts multipart/form-data with one or many files, validates each,
stores it via the pluggable storage backend, hashes it (SHA-256, feeds Module 6
Blockchain/Duplicate checks later), and returns metadata for preview.
"""
import os
import uuid
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select, text, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.models import (
    User, Certificate,
    OCRData, DocumentType, VerificationResult,
    FraudAnalysis, TrustScore, FinalPrediction, VerificationReport,
)
from app.schemas.certificate_schemas import (
    CertificateResponse, CertificateUploadBatchResponse, CertificateGroupLinkRequest,
    CertificateHistoryResponse,
)
from app.services.storage_service import get_storage_backend
from app.utils.file_validation import validate_certificate_file
from app.api.deps import (
    get_current_verified_user, get_current_verified_user_flexible,
    get_owned_certificate, normalize_cert_id,
)

logger = logging.getLogger("certiverify.certificates")

router = APIRouter(prefix="/api/v1/certificates", tags=["Certificate Upload"])


@router.post("/upload", response_model=CertificateUploadBatchResponse, status_code=status.HTTP_201_CREATED)
async def upload_certificates(
    files: list[UploadFile] = File(..., description="One or more certificate files (PDF/JPG/JPEG/PNG)"),
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Accepts multiple files in one request (e.g. Degree + Marksheet + Resume)
    and links them under a single `group_id` so Module 5 (Document Comparison)
    can cross-check them against each other.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")
    if len(files) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 files per upload batch.")

    storage = get_storage_backend()
    group_id = str(uuid.uuid4())
    saved_certificates: list[Certificate] = []

    for file in files:
        await validate_certificate_file(file)

        storage_path, size_bytes, sha256_hash = await storage.save(file, subdir=f"certificates/{user.id}")
        ext = os.path.splitext(file.filename or "")[1].lower().lstrip(".")

        cert = Certificate(
            organization_id=user.organization_id,
            owner_id=user.id,
            original_filename=file.filename,
            storage_path=storage_path,
            file_type=ext,
            file_size_bytes=size_bytes,
            sha256_hash=sha256_hash,
            group_id=group_id,
        )
        db.add(cert)
        saved_certificates.append(cert)

    await db.commit()
    for cert in saved_certificates:
        await db.refresh(cert)

    from app.models.models import VerificationJob, JobStatus, PipelineStage
    from app.services.job_runner import enqueue_verification_job

    created_jobs = []
    for cert in saved_certificates:
        job = VerificationJob(
            organization_id=user.organization_id,
            certificate_id=cert.id,
            status=JobStatus.QUEUED,
            current_stage=PipelineStage.QUEUED,
            progress_percentage=0,
            stage_states={},
        )
        db.add(job)
        created_jobs.append(job)
    
    await db.commit()

    for job_obj in created_jobs:
        enqueue_verification_job(job_obj.id)

    from app.services.audit_service import log_audit_event
    await log_audit_event(
        db,
        action="certificate:upload",
        entity_type="certificate",
        actor_user_id=user.id,
        organization_id=user.organization_id,
        entity_id=group_id,
        metadata_json={"batch_size": len(saved_certificates), "group_id": group_id},
    )

    return CertificateUploadBatchResponse(group_id=group_id, certificates=saved_certificates)



@router.get("", response_model=list[CertificateResponse])
@router.get("/", response_model=list[CertificateResponse], include_in_schema=False)
async def list_my_certificates(
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Certificate).where(Certificate.owner_id == user.id).order_by(Certificate.uploaded_at.desc())
    )
    return result.scalars().all()


@router.get("/history", response_model=list[CertificateHistoryResponse])
async def list_certificate_history(
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns history of all verified certificates for the logged-in user with actual
    persisted database records (certificate_id, filename, document_type, trust_score,
    prediction, status, timestamp, report_reference).
    """
    certs_result = await db.execute(
        select(Certificate)
        .where(
            Certificate.owner_id == user.id,
            Certificate.is_history_hidden.isnot(True),
        )
        .order_by(Certificate.uploaded_at.desc())
    )
    certs = certs_result.scalars().all()
    if not certs:
        return []

    cert_ids = [c.id for c in certs]

    def _map_by_cert_id(rows):
        return {r.certificate_id: r for r in rows}

    doc_types = _map_by_cert_id((await db.execute(select(DocumentType).where(DocumentType.certificate_id.in_(cert_ids)))).scalars().all())
    trust_scores = _map_by_cert_id((await db.execute(select(TrustScore).where(TrustScore.certificate_id.in_(cert_ids)))).scalars().all())
    predictions = _map_by_cert_id((await db.execute(select(FinalPrediction).where(FinalPrediction.certificate_id.in_(cert_ids)))).scalars().all())
    reports = _map_by_cert_id((await db.execute(select(VerificationReport).where(VerificationReport.certificate_id.in_(cert_ids)))).scalars().all())
    verifications = _map_by_cert_id((await db.execute(select(VerificationResult).where(VerificationResult.certificate_id.in_(cert_ids)))).scalars().all())

    history = []
    for c in certs:
        dt = doc_types.get(c.id)
        ts = trust_scores.get(c.id)
        pred = predictions.get(c.id)
        rep = reports.get(c.id)
        vr = verifications.get(c.id)

        dt_str = None
        if dt:
            dt_str = dt.predicted_type.value if hasattr(dt.predicted_type, "value") else str(dt.predicted_type)

        pred_str = pred.label if pred else None
        ts_val = round(ts.score, 1) if (ts and ts.score is not None) else None

        status_str = "COMPLETED" if (vr or pred or ts) else "PENDING"
        rep_ref = rep.verification_id if rep else None

        history.append(CertificateHistoryResponse(
            certificate_id=c.id,
            filename=c.original_filename,
            file_type=c.file_type,
            document_type=dt_str,
            trust_score=ts_val,
            prediction=pred_str,
            status=status_str,
            timestamp=c.uploaded_at,
            report_reference=rep_ref,
        ))

    return history


@router.get("/{certificate_id}", response_model=CertificateResponse)
async def get_certificate(
    certificate_id: str,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    cert = await _get_owned_certificate(certificate_id, user, db)
    return cert


@router.get("/{certificate_id}/preview")
async def preview_certificate(
    certificate_id: str,
    user: User = Depends(get_current_verified_user_flexible),
    db: AsyncSession = Depends(get_db),
):
    cert = await _get_owned_certificate(certificate_id, user, db)
    storage = get_storage_backend()

    contents = await storage.read(cert.storage_path)

    media_types = {"pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}
    media_type = media_types.get(cert.file_type, "application/octet-stream")

    return StreamingResponse(
        iter([contents]),
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{cert.original_filename}"'},
    )


@router.delete("/history/{certificate_id}")
@router.delete("/{certificate_id}/history", include_in_schema=False)
async def delete_certificate_history_entry(
    certificate_id: str,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Deletes an entry from Verification History by hiding it from the chronological history view.

    Enterprise Data Integrity Rules:
    - Does NOT delete the underlying Certificate record.
    - Does NOT delete the original uploaded document / PDF in storage.
    - Does NOT delete OCR data, verification results, fraud analysis, trust scores, or reports.
    - Does NOT delete verification jobs or audit logs.
    - Enforces user ownership and organization tenant access.
    - Only affects the targeted history entry (certificate_id), leaving other entries intact.
    - Commits transaction safely and rolls back on failure.
    - Records an audit log event for compliance tracking.
    """
    # 1. Look up the certificate & verify tenancy/ownership
    cert = await get_owned_certificate(certificate_id, user, db)

    role_str = str(user.role.value if hasattr(user.role, "value") else user.role).lower()
    if "admin" not in role_str and str(cert.owner_id) != str(user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Only the certificate owner or an admin can delete this history entry.",
        )

    # 3. Check if already deleted/hidden from history
    if cert.is_history_hidden:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Verification history entry not found or already deleted.",
        )

    # 4. Apply soft-delete / history visibility removal
    cert.is_history_hidden = True
    cert.history_deleted_at = datetime.utcnow()

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error("Failed to delete verification history entry %s: %s", certificate_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error while deleting verification history entry.",
        )

    # 5. Record compliance audit log event
    try:
        from app.services.audit_service import log_audit_event
        await log_audit_event(
            db,
            action="certificate:history_delete",
            entity_type="certificate_history",
            actor_user_id=user.id,
            organization_id=cert.organization_id or user.organization_id,
            entity_id=cert.id,
            metadata_json={
                "certificate_id": cert.id,
                "filename": cert.original_filename,
                "action": "hide_from_history",
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
    except Exception as exc:
        logger.warning("Audit logging failed for history delete: %s", exc)

    logger.info("Verification history entry %s hidden from history by user %s", cert.id, user.id)

    return {
        "success": True,
        "message": "Verification history entry deleted successfully.",
        "certificate_id": cert.id,
    }


@router.delete("/{certificate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_certificate(
    certificate_id: str,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Deletes the certificate and all its related child rows (OCR, verification,
    fraud analysis, trust score, prediction, report) and auxiliary files (stored doc,
    ELA heatmap, report PDF) before removing the parent certificate record.
    Only the owner can delete their own certificate (enforced by _get_owned_certificate).
    """
    cert = await _get_owned_certificate(certificate_id, user, db)
    role_str = str(user.role.value if hasattr(user.role, "value") else user.role).lower()
    if "admin" not in role_str and str(cert.owner_id) != str(user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Only the certificate owner or an admin can delete this certificate.",
        )
    logger.info("DELETE START | certificate=%s | owner=%s", cert.id, user.id)

    storage = get_storage_backend()

    # 1. Clean up duplicate references in other certificates' verification_results
    try:
        cid_str = str(cert.id)
        cid_nohyphen = cid_str.replace("-", "")
        await db.execute(
            text("UPDATE verification_results SET duplicate_of_certificate_id = NULL WHERE duplicate_of_certificate_id = :cid OR duplicate_of_certificate_id = :cid_nohyphen"),
            {"cid": cid_str, "cid_nohyphen": cid_nohyphen},
        )
    except Exception as exc:
        logger.warning("Could not clear duplicate references pointing to cert %s: %s", cert.id, exc)

    # 2. Clean up group comparison record if no other certificates remain in the group
    if cert.group_id:
        try:
            other_in_group = await db.execute(
                select(Certificate).where(Certificate.group_id == cert.group_id, Certificate.id != cert.id)
            )
            if not other_in_group.scalars().first():
                gid_str = str(cert.group_id)
                gid_nohyphen = gid_str.replace("-", "")
                await db.execute(
                    text("DELETE FROM document_comparisons WHERE group_id = :gid OR group_id = :gid_nohyphen"),
                    {"gid": gid_str, "gid_nohyphen": gid_nohyphen},
                )
                logger.info("Deleted document_comparisons for group %s", cert.group_id)
        except Exception as exc:
            logger.warning("Could not clean up group comparison for cert %s: %s", cert.id, exc)

    # 3. Clean up associated auxiliary files: ELA heatmap & Report PDF
    try:
        verif_res = await db.execute(
            select(VerificationResult.ela_heatmap_path).where(VerificationResult.certificate_id == cert.id)
        )
        ela_path = verif_res.scalar_one_or_none()
        if ela_path:
            try:
                await storage.delete(ela_path)
                logger.info("Deleted ELA heatmap file %s", ela_path)
            except Exception as exc:
                logger.warning("Could not delete ELA heatmap file %s: %s", ela_path, exc)
    except Exception as exc:
        logger.warning("Error looking up ELA heatmap for cert %s: %s", cert.id, exc)

    try:
        report_res = await db.execute(
            select(VerificationReport.pdf_path).where(VerificationReport.certificate_id == cert.id)
        )
        pdf_path = report_res.scalar_one_or_none()
        if pdf_path:
            try:
                if os.path.exists(pdf_path):
                    os.remove(pdf_path)
                else:
                    await storage.delete(pdf_path)
                logger.info("Deleted report PDF file %s", pdf_path)
            except Exception as exc:
                logger.warning("Could not delete report PDF file %s: %s", pdf_path, exc)
    except Exception as exc:
        logger.warning("Error looking up report PDF for cert %s: %s", cert.id, exc)

    # 4. Clean up uploaded primary certificate document file
    try:
        if cert.storage_path:
            await storage.delete(cert.storage_path)
            logger.info("Deleted file %s", cert.storage_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not delete file %s: %s", cert.storage_path, exc)

    # 5. Delete child rows in reverse-dependency order using type-compiled delete statements
    child_models = [
        VerificationReport,
        FinalPrediction,
        TrustScore,
        FraudAnalysis,
        VerificationResult,
        OCRData,
        DocumentType,
    ]
    for model in child_models:
        try:
            result = await db.execute(delete(model).where(model.certificate_id == cert.id))
            if result.rowcount:  # type: ignore[union-attr]
                logger.info("Deleted %d row(s) from %s for certificate %s",
                            result.rowcount, model.__tablename__, cert.id)
        except Exception as exc:
            logger.warning("Could not delete from %s for cert %s: %s",
                           model.__tablename__, cert.id, exc)

    # 6. Delete parent certificate row using type-compiled delete statement
    res = await db.execute(delete(Certificate).where(Certificate.id == cert.id))
    logger.info("Deleted %d certificate row(s) for ID %s", res.rowcount, cert.id)
    await db.commit()

    from app.services.audit_service import log_audit_event
    await log_audit_event(
        db,
        action="certificate:delete",
        entity_type="certificate",
        actor_user_id=user.id,
        organization_id=user.organization_id,
        entity_id=cert.id,
        metadata_json={"filename": cert.original_filename},
    )

    logger.info("DELETE END | certificate %s deleted by user %s", cert.id, user.id)
    return None



@router.post("/link-group", response_model=list[CertificateResponse])
async def link_certificates_into_group(
    payload: CertificateGroupLinkRequest,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Retroactively group separately-uploaded documents (e.g. resume added later) for Module 5 comparison."""
    normalized_ids = [normalize_cert_id(cid) for cid in payload.certificate_ids]
    result = await db.execute(
        select(Certificate).where(
            Certificate.id.in_(normalized_ids), Certificate.owner_id == user.id
        )
    )
    certs = result.scalars().all()
    if len(certs) != len(payload.certificate_ids):
        raise HTTPException(status_code=404, detail="One or more certificates not found.")

    shared_group_id = certs[0].group_id or str(uuid.uuid4())
    for cert in certs:
        cert.group_id = shared_group_id
    await db.commit()
    for cert in certs:
        await db.refresh(cert)
    return certs


async def _get_owned_certificate(certificate_id: str, user: User, db: AsyncSession) -> Certificate:
    return await get_owned_certificate(certificate_id, user, db)

