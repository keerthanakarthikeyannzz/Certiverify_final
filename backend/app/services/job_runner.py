import asyncio
import logging
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import database
from app.models.models import (
    User, Certificate, VerificationJob, JobStatus, PipelineStage,
    DocumentType, OCRData, VerificationResult, FraudAnalysis, TrustScore,
)
from app.api.document_type import classify_certificate
from app.api.ocr import extract_ocr
from app.api.verification import (
    run_qr_check, run_blockchain_verification, run_tampering_detection, run_duplicate_detection
)
from app.api.fraud import run_fraud_analysis
from app.api.trust_score import run_trust_score
from app.api.prediction import run_prediction
from app.services.audit_service import log_audit_event
from app.services.evidence_service import (
    emit_document_analysis_evidence,
    emit_ocr_evidence,
    emit_qr_evidence,
    emit_blockchain_evidence,
    emit_tampering_evidence,
    emit_duplicate_evidence,
    emit_fraud_evidence,
    emit_trust_score_evidence,
)


logger = logging.getLogger("certiverify.job_runner")


async def execute_verification_pipeline(job_id: str, is_retry: bool = False):
    """
    Asynchronously processes all pipeline stages for a VerificationJob:
    1. DOCUMENT_ANALYSIS
    2. OCR
    3. QR_VERIFICATION
    4. BLOCKCHAIN_VERIFICATION
    5. TAMPER_ANALYSIS
    6. DUPLICATE_DETECTION
    7. FRAUD_ANALYSIS
    8. TRUST_SCORE (and Final Prediction)
    9. COMPLETED
    """
    async with database.AsyncSessionLocal() as db:
        res = await db.execute(select(VerificationJob).where(VerificationJob.id == job_id))
        job = res.scalar_one_or_none()
        if not job:
            logger.error("Job %s not found in DB", job_id)
            return

        if job.status == JobStatus.COMPLETED:
            logger.info("Job %s already COMPLETED. Skipping execution.", job_id)
            return

        cert_res = await db.execute(select(Certificate).where(Certificate.id == job.certificate_id))
        cert = cert_res.scalar_one_or_none()
        if not cert:
            job.status = JobStatus.FAILED
            job.error_details = "Certificate record missing"
            await db.commit()
            return

        user_res = await db.execute(select(User).where(User.id == cert.owner_id))
        user = user_res.scalar_one_or_none()
        if not user:
            job.status = JobStatus.FAILED
            job.error_details = "Certificate owner user missing"
            await db.commit()
            return

        user_id = user.id
        cert_id = cert.id
        org_id = job.organization_id or user.organization_id

        job.status = JobStatus.PROCESSING
        if not job.started_at:
            job.started_at = datetime.utcnow()
        if is_retry:
            job.retry_count += 1

        stage_states = job.stage_states or {}
        await db.commit()

        await log_audit_event(
            db,
            action="verification:started",
            entity_type="verification_job",
            actor_user_id=user.id,
            organization_id=job.organization_id,
            entity_id=job.id,
            metadata_json={"certificate_id": cert.id, "is_retry": is_retry},
        )

        stages_config = [
            (PipelineStage.DOCUMENT_ANALYSIS, 10, "Document Analysis"),
            (PipelineStage.OCR, 25, "OCR Extraction"),
            (PipelineStage.QR_VERIFICATION, 40, "QR Code Verification"),
            (PipelineStage.BLOCKCHAIN_VERIFICATION, 50, "Blockchain Verification"),
            (PipelineStage.TAMPER_ANALYSIS, 65, "Tampering Analysis"),
            (PipelineStage.DUPLICATE_DETECTION, 75, "Duplicate Detection"),
            (PipelineStage.FRAUD_ANALYSIS, 85, "Fraud Analysis"),
            (PipelineStage.TRUST_SCORE, 95, "Trust Score & Prediction"),
        ]

        try:
            for stage_enum, progress_pct, stage_label in stages_config:
                stage_key = stage_enum.value

                # Safe Retry Check: if stage was already completed during previous run, skip re-running it
                if is_retry and stage_states.get(stage_key, {}).get("status") == "COMPLETED":
                    logger.info("Skipping already completed stage %s for job %s", stage_key, job_id)
                    continue

                job.current_stage = stage_enum
                job.progress_percentage = progress_pct
                stage_states[stage_key] = {
                    "status": "PROCESSING",
                    "label": stage_label,
                    "started_at": datetime.utcnow().isoformat(),
                }
                job.stage_states = dict(stage_states)
                await db.commit()

                if stage_enum == PipelineStage.DOCUMENT_ANALYSIS:
                    await classify_certificate(cert.id, user, db)
                    doc_res = await db.execute(select(DocumentType).where(DocumentType.certificate_id == cert.id).order_by(DocumentType.id.desc()))
                    await emit_document_analysis_evidence(db, cert, doc_res.scalars().first(), verification_job_id=job.id, actor_user_id=user.id)

                elif stage_enum == PipelineStage.OCR:
                    await extract_ocr(certificate_id=cert.id, doc_type=None, force_refresh=False, user=user, db=db)
                    ocr_res = await db.execute(select(OCRData).where(OCRData.certificate_id == cert.id).order_by(OCRData.id.desc()))
                    await emit_ocr_evidence(db, cert, ocr_res.scalars().first(), verification_job_id=job.id, actor_user_id=user.id)

                elif stage_enum == PipelineStage.QR_VERIFICATION:
                    await run_qr_check(cert.id, user, db)
                    vr_res = await db.execute(select(VerificationResult).where(VerificationResult.certificate_id == cert.id).order_by(VerificationResult.id.desc()))
                    vr_obj = vr_res.scalars().first()
                    await emit_qr_evidence(db, cert, vr_obj, verification_job_id=job.id, actor_user_id=user.id)

                    if vr_obj and not vr_obj.qr_present:
                        stage_states[stage_key]["status"] = "NOT_APPLICABLE"
                        stage_states[stage_key]["details"] = vr_obj.qr_warning or "No QR code detected on document"
                    elif vr_obj and vr_obj.qr_valid is False:
                        stage_states[stage_key]["status"] = "FAILED"
                        stage_states[stage_key]["details"] = vr_obj.qr_warning or "QR validation failed"
                    else:
                        stage_states[stage_key]["status"] = "COMPLETED"
                        stage_states[stage_key]["details"] = "QR verified successfully"

                elif stage_enum == PipelineStage.BLOCKCHAIN_VERIFICATION:
                    await run_blockchain_verification(cert.id, user, db)
                    vr_res = await db.execute(select(VerificationResult).where(VerificationResult.certificate_id == cert.id).order_by(VerificationResult.id.desc()))
                    vr_obj = vr_res.scalars().first()
                    await emit_blockchain_evidence(db, cert, vr_obj, verification_job_id=job.id, actor_user_id=user.id)
                    if vr_obj and vr_obj.blockchain_status == "NOT_APPLICABLE":
                        stage_states[stage_key]["status"] = "NOT_APPLICABLE"
                        stage_states[stage_key]["details"] = "Blockchain not configured"
                    elif vr_obj and vr_obj.blockchain_status in ("UNREACHABLE", "MISMATCH"):
                        stage_states[stage_key]["status"] = "FAILED"
                        stage_states[stage_key]["details"] = f"Blockchain check failed: {vr_obj.blockchain_status}"
                    else:
                        stage_states[stage_key]["status"] = "COMPLETED"
                        stage_states[stage_key]["details"] = f"Blockchain: {vr_obj.blockchain_status if vr_obj else 'done'}"

                elif stage_enum == PipelineStage.TAMPER_ANALYSIS:
                    await run_tampering_detection(cert.id, user, db)
                    vr_res = await db.execute(select(VerificationResult).where(VerificationResult.certificate_id == cert.id).order_by(VerificationResult.id.desc()))
                    vr_obj = vr_res.scalars().first()
                    await emit_tampering_evidence(db, cert, vr_obj, verification_job_id=job.id, actor_user_id=user.id)

                elif stage_enum == PipelineStage.DUPLICATE_DETECTION:
                    await run_duplicate_detection(cert.id, user, db)
                    vr_res = await db.execute(select(VerificationResult).where(VerificationResult.certificate_id == cert.id).order_by(VerificationResult.id.desc()))
                    await emit_duplicate_evidence(db, cert, vr_res.scalars().first(), verification_job_id=job.id, actor_user_id=user.id)

                elif stage_enum == PipelineStage.FRAUD_ANALYSIS:
                    await run_fraud_analysis(cert.id, user, db)
                    fa_res = await db.execute(select(FraudAnalysis).where(FraudAnalysis.certificate_id == cert.id).order_by(FraudAnalysis.id.desc()))
                    await emit_fraud_evidence(db, cert, fa_res.scalars().first(), verification_job_id=job.id, actor_user_id=user.id)

                elif stage_enum == PipelineStage.TRUST_SCORE:
                    await run_trust_score(cert.id, user, db)
                    ts_res = await db.execute(select(TrustScore).where(TrustScore.certificate_id == cert.id).order_by(TrustScore.id.desc()))
                    await emit_trust_score_evidence(db, cert, ts_res.scalars().first(), verification_job_id=job.id, actor_user_id=user.id)
                    await run_prediction(cert.id, user, db)
                    try:
                        from app.api.report import generate_report
                        await generate_report(certificate_id=cert.id, user=user, db=db)
                    except Exception as rep_err:
                        logger.warning("Auto report generation for job %s had non-fatal error: %s", job_id, rep_err)

                if stage_states[stage_key].get("status") not in ("NOT_APPLICABLE", "SKIPPED", "FAILED"):
                    stage_states[stage_key]["status"] = "COMPLETED"
                stage_states[stage_key]["completed_at"] = datetime.utcnow().isoformat()
                job.stage_states = dict(stage_states)
                await db.commit()

                await log_audit_event(
                    db,
                    action="verification:stage_completed",
                    entity_type="verification_job",
                    actor_user_id=user.id,
                    organization_id=job.organization_id,
                    entity_id=job.id,
                    metadata_json={"stage": stage_key, "progress": progress_pct},
                )

            # Check for tamper alert
            vr_check = await db.execute(
                select(VerificationResult)
                .where(VerificationResult.certificate_id == cert.id)
                .order_by(VerificationResult.id.desc())
            )
            vr_obj = vr_check.scalars().first()
            tampering_score_val = getattr(vr_obj, "tampering_score", 0.0) if vr_obj else 0.0
            if tampering_score_val is None:
                tampering_score_val = 0.0
            is_tampered_val = bool(getattr(vr_obj, "is_tampered", False)) if vr_obj else False

            if vr_obj and (is_tampered_val or float(tampering_score_val) >= 50.0):
                from app.services.webhook_service import dispatch_webhook_event
                await dispatch_webhook_event(
                    db=db,
                    organization_id=job.organization_id,
                    event_type="tamper.detected",
                    payload={
                        "job_id": job.id,
                        "certificate_id": cert.id,
                        "tampering_score": float(tampering_score_val),
                        "is_tampered": is_tampered_val,
                    },
                )

            # Check for fraud alert
            fa_check = await db.execute(
                select(FraudAnalysis)
                .where(FraudAnalysis.certificate_id == cert.id)
                .order_by(FraudAnalysis.id.desc())
            )
            fa_obj = fa_check.scalars().first()
            fraud_prob_val = getattr(fa_obj, "fraud_probability", 0.0) if fa_obj else 0.0
            if fraud_prob_val is None:
                fraud_prob_val = 0.0

            if fa_obj and float(fraud_prob_val) >= 0.6:
                from app.services.webhook_service import dispatch_webhook_event
                await dispatch_webhook_event(
                    db=db,
                    organization_id=job.organization_id,
                    event_type="fraud.alert",
                    payload={
                        "job_id": job.id,
                        "certificate_id": cert.id,
                        "fraud_probability": float(fraud_prob_val),
                        "risk_level": getattr(fa_obj, "risk_level", "HIGH"),
                    },
                )

            job.status = JobStatus.COMPLETED
            job.current_stage = PipelineStage.COMPLETED
            job.progress_percentage = 100
            job.completed_at = datetime.utcnow()
            job.error_details = None
            job.failed_stage = None
            await db.commit()

            await log_audit_event(
                db,
                action="verification:completed",
                entity_type="verification_job",
                actor_user_id=user.id,
                organization_id=job.organization_id,
                entity_id=job.id,
                metadata_json={"certificate_id": cert.id},
            )

            from app.services.webhook_service import dispatch_webhook_event
            await dispatch_webhook_event(
                db=db,
                organization_id=job.organization_id,
                event_type="verification.completed",
                payload={
                    "job_id": job.id,
                    "certificate_id": cert.id,
                    "status": "COMPLETED",
                    "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                },
            )

        except Exception as exc:
            import traceback
            tb_str = traceback.format_exc()
            logger.error("Job %s failed at stage %s: %s\n%s", job_id, getattr(job, "current_stage", "unknown"), exc, tb_str)
            failed_stage_name = job.current_stage.value if hasattr(getattr(job, "current_stage", None), "value") else str(getattr(job, "current_stage", "unknown"))

            try:
                await db.rollback()
            except Exception:
                pass

            res = await db.execute(select(VerificationJob).where(VerificationJob.id == job_id))
            job = res.scalar_one_or_none()
            if not job:
                return

            job.status = JobStatus.FAILED
            job.failed_stage = failed_stage_name

            if isinstance(exc, HTTPException):
                if isinstance(exc.detail, dict):
                    err_reason = exc.detail.get("error") or exc.detail.get("message") or str(exc.detail)
                else:
                    err_reason = str(exc.detail)
            else:
                err_reason = str(exc)

            job.error_details = err_reason

            stage_states = dict(job.stage_states or {})
            if failed_stage_name in stage_states:
                stage_states[failed_stage_name]["status"] = "FAILED"
                stage_states[failed_stage_name]["error"] = err_reason
                job.stage_states = dict(stage_states)

            await db.commit()

            await log_audit_event(
                db,
                action="verification:failed",
                entity_type="verification_job",
                actor_user_id=user_id,
                organization_id=org_id,
                entity_id=job_id,
                metadata_json={"failed_stage": failed_stage_name, "error": str(exc)},
            )

            from app.services.webhook_service import dispatch_webhook_event
            await dispatch_webhook_event(
                db=db,
                organization_id=org_id,
                event_type="verification.failed",
                payload={
                    "job_id": job_id,
                    "certificate_id": cert_id,
                    "failed_stage": failed_stage_name,
                    "error": str(exc),
                },
            )


def enqueue_verification_job(job_id: str, is_retry: bool = False):
    """
    Spawns background task execution without blocking the API HTTP request thread.
    """
    asyncio.create_task(execute_verification_pipeline(job_id, is_retry=is_retry))
