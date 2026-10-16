from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.models import User, Certificate, VerificationJob, JobStatus, PipelineStage
from app.schemas.job_schemas import JobResponse, JobCreateResponse
from app.api.deps import get_current_verified_user, verify_tenant_access, require_permission
from app.services.job_runner import enqueue_verification_job
from app.services.audit_service import log_audit_event

router = APIRouter(prefix="/api/v1", tags=["Verification Jobs"])


@router.post(
    "/certificates/{certificate_id}/verify-async",
    response_model=JobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@router.post(
    "/certificates/{certificate_id}/jobs",
    response_model=JobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_verification_job(
    certificate_id: str,
    current_user: User = Depends(require_permission("certificate:verify")),
    db: AsyncSession = Depends(get_db),
):
    """
    Enqueues an asynchronous verification job for the certificate and returns HTTP 202 Accepted immediately.
    """
    cert_res = await db.execute(select(Certificate).where(Certificate.id == certificate_id))
    cert = cert_res.scalar_one_or_none()
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")

    verify_tenant_access(current_user, cert.organization_id, cert.owner_id)

    # Create new VerificationJob entry
    job = VerificationJob(
        organization_id=current_user.organization_id,
        certificate_id=cert.id,
        status=JobStatus.QUEUED,
        current_stage=PipelineStage.QUEUED,
        progress_percentage=0,
        stage_states={},
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    await log_audit_event(
        db,
        action="verification:queued",
        entity_type="verification_job",
        actor_user_id=current_user.id,
        organization_id=current_user.organization_id,
        entity_id=job.id,
        metadata_json={"certificate_id": cert.id},
    )

    # Spawn background task execution
    enqueue_verification_job(job.id)

    return JobCreateResponse(
        job_id=job.id,
        certificate_id=cert.id,
        status=job.status.value,
        current_stage=job.current_stage.value,
        progress_percentage=0,
        message="Verification job enqueued successfully",
    )


@router.get("/jobs/{job_id}/status", response_model=JobResponse)
async def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieves verification job status and stage progress telemetry.
    Enforces strict organization tenant isolation.
    """
    res = await db.execute(select(VerificationJob).where(VerificationJob.id == job_id))
    job = res.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Verification job not found")

    cert_res = await db.execute(select(Certificate.owner_id).where(Certificate.id == job.certificate_id))
    owner_id = cert_res.scalar_one_or_none()
    verify_tenant_access(current_user, job.organization_id, owner_id)

    job_dict = {
        "id": job.id,
        "job_id": job.id,
        "certificate_id": job.certificate_id,
        "organization_id": job.organization_id,
        "status": job.status.value if hasattr(job.status, "value") else str(job.status),
        "current_stage": job.current_stage.value if hasattr(job.current_stage, "value") else str(job.current_stage),
        "progress_percentage": job.progress_percentage,
        "stage_states": job.stage_states,
        "error_details": job.error_details,
        "failed_stage": job.failed_stage,
        "retry_count": job.retry_count,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
    }
    return job_dict


@router.get("/certificates/{certificate_id}/job-status", response_model=JobResponse)
async def get_latest_job_for_certificate(
    certificate_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieves the latest verification job status for a given certificate.
    """
    cert_res = await db.execute(select(Certificate).where(Certificate.id == certificate_id))
    cert = cert_res.scalar_one_or_none()
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")

    verify_tenant_access(current_user, cert.organization_id, cert.owner_id)

    res = await db.execute(
        select(VerificationJob)
        .where(VerificationJob.certificate_id == certificate_id)
        .order_by(VerificationJob.created_at.desc())
    )
    job = res.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="No verification job found for this certificate")

    job_dict = {
        "id": job.id,
        "job_id": job.id,
        "certificate_id": job.certificate_id,
        "organization_id": job.organization_id,
        "status": job.status.value if hasattr(job.status, "value") else str(job.status),
        "current_stage": job.current_stage.value if hasattr(job.current_stage, "value") else str(job.current_stage),
        "progress_percentage": job.progress_percentage,
        "stage_states": job.stage_states,
        "error_details": job.error_details,
        "failed_stage": job.failed_stage,
        "retry_count": job.retry_count,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
    }
    return job_dict


@router.post("/jobs/{job_id}/retry", response_model=JobCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def retry_verification_job(
    job_id: str,
    current_user: User = Depends(require_permission("certificate:verify")),
    db: AsyncSession = Depends(get_db),
):
    """
    Retries a failed verification job, resuming from the failed stage.
    """
    res = await db.execute(select(VerificationJob).where(VerificationJob.id == job_id))
    job = res.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Verification job not found")

    cert_res = await db.execute(select(Certificate.owner_id).where(Certificate.id == job.certificate_id))
    owner_id = cert_res.scalar_one_or_none()
    verify_tenant_access(current_user, job.organization_id, owner_id)

    if job.status != JobStatus.FAILED:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot retry job in status '{job.status}'. Only FAILED jobs can be retried.",
        )

    job.status = JobStatus.QUEUED
    job.error_details = None
    await db.commit()
    await db.refresh(job)

    await log_audit_event(
        db,
        action="verification:retry_queued",
        entity_type="verification_job",
        actor_user_id=current_user.id,
        organization_id=current_user.organization_id,
        entity_id=job.id,
        metadata_json={"retry_count": job.retry_count + 1},
    )

    enqueue_verification_job(job.id, is_retry=True)

    return JobCreateResponse(
        job_id=job.id,
        certificate_id=job.certificate_id,
        status=job.status.value,
        current_stage=job.current_stage.value,
        progress_percentage=job.progress_percentage,
        message="Verification job retry enqueued successfully",
    )
