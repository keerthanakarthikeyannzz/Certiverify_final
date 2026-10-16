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
                    doc_res = await db.execute(select(DocumentType).where(DocumentType.certificate_id == cert.id))
                    await emit_document_analysis_evidence(db, cert, doc_res.scalar_one_or_none(), verification_job_id=job.id, actor_user_id=user.id)

                elif stage_enum == PipelineStage.OCR:
                    await extract_ocr(cert.id, None, user, db)
                    ocr_res = await db.execute(select(OCRData).where(OCRData.certificate_id == cert.id))
                    await emit_ocr_evidence(db, cert, ocr_res.scalar_one_or_none(), verification_job_id=job.id, actor_user_id=user.id)

                elif stage_enum == PipelineStage.QR_VERIFICATION:
                    await run_qr_check(cert.id, user, db)
                    vr_res = await db.execute(select(VerificationResult).where(VerificationResult.certificate_id == cert.id))
                    vr_obj = vr_res.scalar_one_or_none()
                    await emit_qr_evidence(db, cert, vr_obj, verification_job_id=job.id, actor_user_id=user.id)
                    
                    # If QR code is present and valid, blockchain lookup may be marked optional/skipped,
                    # but Tampering Analysis MUST always run to check visual forgery/manipulation.
                    if vr_obj and vr_obj.qr_present and vr_obj.qr_valid:
                        logger.info("QR code verified for certificate %s. Blockchain marked optional.", cert.id)
                        if not vr_obj.blockchain_status or vr_obj.blockchain_status == "unavailable":
                            vr_obj.blockchain_status = "skipped: verified_via_qr"
                            await db.commit()

                        stage_states[PipelineStage.BLOCKCHAIN_VERIFICATION.value] = {
                            "status": "SKIPPED",
                            "label": "Blockchain Verification",
                            "completed_at": datetime.utcnow().isoformat(),
                            "details": "Skipped — Verified via QR",
                        }

                elif stage_enum == PipelineStage.BLOCKCHAIN_VERIFICATION:
                    if stage_states.get(stage_key, {}).get("status") == "SKIPPED":
                        logger.info("Skipping stage %s for job %s (QR verified)", stage_key, job_id)
                        continue
                    await run_blockchain_verification(cert.id, user, db)
                    vr_res = await db.execute(select(VerificationResult).where(VerificationResult.certificate_id == cert.id))
                    await emit_blockchain_evidence(db, cert, vr_res.scalar_one_or_none(), verification_job_id=job.id, actor_user_id=user.id)

                elif stage_enum == PipelineStage.TAMPER_ANALYSIS:
                    await run_tampering_detection(cert.id, user, db)
                    vr_res = await db.execute(select(VerificationResult).where(VerificationResult.certificate_id == cert.id))
                    await emit_tampering_evidence(db, cert, vr_res.scalar_one_or_none(), verification_job_id=job.id, actor_user_id=user.id)

                elif stage_enum == PipelineStage.DUPLICATE_DETECTION:
                    await run_duplicate_detection(cert.id, user, db)
                    vr_res = await db.execute(select(VerificationResult).where(VerificationResult.certificate_id == cert.id))
                    await emit_duplicate_evidence(db, cert, vr_res.scalar_one_or_none(), verification_job_id=job.id, actor_user_id=user.id)

                elif stage_enum == PipelineStage.FRAUD_ANALYSIS:
                    await run_fraud_analysis(cert.id, user, db)
                    fa_res = await db.execute(select(FraudAnalysis).where(FraudAnalysis.certificate_id == cert.id))
                    await emit_fraud_evidence(db, cert, fa_res.scalar_one_or_none(), verification_job_id=job.id, actor_user_id=user.id)

                elif stage_enum == PipelineStage.TRUST_SCORE:
                    await run_trust_score(cert.id, user, db)
                    ts_res = await db.execute(select(TrustScore).where(TrustScore.certificate_id == cert.id))
                    await emit_trust_score_evidence(db, cert, ts_res.scalar_one_or_none(), verification_job_id=job.id, actor_user_id=user.id)
                    await run_prediction(cert.id, user, db)

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
            vr_check = await db.execute(select(VerificationResult).where(VerificationResult.certificate_id == cert.id))
            vr_obj = vr_check.scalar_one_or_none()
            if vr_obj and (getattr(vr_obj, "is_tampered", False) or getattr(vr_obj, "tampering_score", 0.0) >= 50.0):
                from app.services.webhook_service import dispatch_webhook_event
                await dispatch_webhook_event(
                    db=db,
                    organization_id=job.organization_id,
                    event_type="tamper.detected",
                    payload={
                        "job_id": job.id,
                        "certificate_id": cert.id,
                        "tampering_score": getattr(vr_obj, "tampering_score", 0.0),
                        "is_tampered": getattr(vr_obj, "is_tampered", False),
                    },
                )

            # Check for fraud alert
            fa_check = await db.execute(select(FraudAnalysis).where(FraudAnalysis.certificate_id == cert.id))
            fa_obj = fa_check.scalar_one_or_none()
            if fa_obj and getattr(fa_obj, "fraud_probability", 0.0) >= 0.6:
                from app.services.webhook_service import dispatch_webhook_event
                await dispatch_webhook_event(
                    db=db,
                    organization_id=job.organization_id,
                    event_type="fraud.alert",
                    payload={
                        "job_id": job.id,
                        "certificate_id": cert.id,
                        "fraud_probability": getattr(fa_obj, "fraud_probability", 0.0),
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
            logger.error("Job %s failed at stage %s: %s\n%s", job_id, job.current_stage, exc, tb_str)
            failed_stage_name = job.current_stage.value if hasattr(job.current_stage, "value") else str(job.current_stage)
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

            if failed_stage_name in stage_states:
                stage_states[failed_stage_name]["status"] = "FAILED"
                stage_states[failed_stage_name]["error"] = err_reason
                job.stage_states = dict(stage_states)

            await db.commit()

            await log_audit_event(
                db,
                action="verification:failed",
                entity_type="verification_job",
                actor_user_id=user.id,
                organization_id=job.organization_id,
                entity_id=job.id,
                metadata_json={"failed_stage": failed_stage_name, "error": str(exc)},
            )

            from app.services.webhook_service import dispatch_webhook_event
            await dispatch_webhook_event(
                db=db,
                organization_id=job.organization_id,
                event_type="verification.failed",
                payload={
                    "job_id": job.id,
                    "certificate_id": cert.id,
                    "failed_stage": failed_stage_name,
                    "error": str(exc),
                },
            )


def enqueue_verification_job(job_id: str, is_retry: bool = False):
    """
    Spawns background task execution without blocking the API HTTP request thread.
    """
    asyncio.create_task(execute_verification_pipeline(job_id, is_retry=is_retry))
