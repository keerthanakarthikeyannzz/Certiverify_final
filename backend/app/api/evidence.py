"""
PHASE 3 - EVIDENCE API ENDPOINTS

GET /api/v1/certificates/{certificate_id}/evidence
  - Supports authentication & strict multi-tenant organization isolation.
  - Supports filtering by evidence_type & verification_job_id.
  - Supports pagination & deterministic sorting.
  - Exposes standardized EvidenceItem objects.
"""
import math
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.models import (
    User, Certificate, EvidenceItem, EvidenceType, VerificationJob
)
from app.schemas.evidence_schemas import (
    EvidenceItemResponse, EvidencePaginatedResponse
)
from app.core.permissions import has_permission, Permission
from app.services.audit_service import log_audit_event
from app.api.deps import get_current_verified_user

router = APIRouter(prefix="/api/v1/certificates", tags=["Evidence Provenance"])


async def _get_authorized_certificate(certificate_id: str, user: User, db: AsyncSession) -> Certificate:
    """Check tenant isolation & RBAC permissions for certificate access."""
    if not has_permission(user.role.value, Permission.CERTIFICATE_READ):
        raise HTTPException(status_code=403, detail="Insufficient permission to view certificate evidence.")

    res = await db.execute(select(Certificate).where(Certificate.id == certificate_id))
    cert = res.scalar_one_or_none()
    if not cert:
        raise HTTPException(status_code=404, detail=f"Certificate '{certificate_id}' not found.")

    # Strict multi-tenant isolation check
    user_org = str(user.organization_id) if user.organization_id else None
    cert_org = str(cert.organization_id) if cert.organization_id else None
    user_id = str(user.id)
    owner_id = str(cert.owner_id)

    if user.role.value != "admin" and owner_id != user_id:
        if cert_org and user_org and cert_org != user_org:
            raise HTTPException(status_code=404, detail=f"Certificate '{certificate_id}' not found.")
        elif not cert_org and owner_id != user_id:
            raise HTTPException(status_code=404, detail=f"Certificate '{certificate_id}' not found.")

    return cert


@router.get("/{certificate_id}/evidence", response_model=EvidencePaginatedResponse)
async def get_certificate_evidence(
    certificate_id: str,
    evidence_type: str | None = Query(None, description="Filter by evidence type (OCR, QR, BLOCKCHAIN, TAMPER, DUPLICATE, STRUCTURE, METADATA, FRAUD, TRUST_SCORE)"),
    verification_job_id: str | None = Query(None, description="Filter by specific verification job run ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve standardized, traceable evidence items backing CertiVerify's verification verdict.
    Enforces authentication, tenant isolation, filtering, and pagination.
    """
    cert = await _get_authorized_certificate(certificate_id, user, db)

    # Base query filtered by certificate_id
    stmt = select(EvidenceItem).where(EvidenceItem.certificate_id == cert.id)

    if evidence_type:
        ev_upper = evidence_type.strip().upper()
        try:
            ev_enum = EvidenceType(ev_upper)
            stmt = stmt.where(EvidenceItem.evidence_type == ev_enum)
        except ValueError:
            # If invalid string passed, match on string value
            stmt = stmt.where(func.upper(EvidenceItem.evidence_type) == ev_upper)

    if verification_job_id:
        stmt = stmt.where(EvidenceItem.verification_job_id == verification_job_id)

    # Total count query
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_res = await db.execute(count_stmt)
    total = total_res.scalar() or 0

    # Deterministic sorting: newest timestamp first, then id
    stmt = stmt.order_by(desc(EvidenceItem.created_at), desc(EvidenceItem.id))

    # Pagination offset
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)

    items_res = await db.execute(stmt)
    raw_items = items_res.scalars().all()

    formatted_items = []
    for item in raw_items:
        ev_type_str = item.evidence_type.value if hasattr(item.evidence_type, "value") else str(item.evidence_type)
        formatted_items.append(
            EvidenceItemResponse(
                id=item.id,
                evidence_id=item.id,
                organization_id=item.organization_id,
                certificate_id=item.certificate_id,
                verification_job_id=item.verification_job_id,
                evidence_type=ev_type_str,
                source=item.source,
                stage=item.stage,
                timestamp=item.timestamp,
                document_hash=item.document_hash,
                algorithm_engine=item.algorithm_engine,
                algorithm_version=item.algorithm_version,
                confidence=item.confidence,
                result=item.result,
                explanation=item.explanation,
                details=item.details,
                created_at=item.created_at,
            )
        )

    total_pages = math.ceil(total / page_size) if total > 0 else 1

    await log_audit_event(
        db,
        action="evidence:viewed",
        entity_type="certificate",
        actor_user_id=user.id,
        organization_id=user.organization_id,
        entity_id=cert.id,
        metadata_json={
            "certificate_id": cert.id,
            "evidence_type_filter": evidence_type,
            "job_filter": verification_job_id,
            "items_returned": len(formatted_items),
        },
    )

    return EvidencePaginatedResponse(
        items=formatted_items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{certificate_id}/evidence/jobs")
async def get_certificate_verification_jobs(
    certificate_id: str,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns historical verification job runs for this certificate to support
    switching between historical verification evidence sets in the UI.
    """
    cert = await _get_authorized_certificate(certificate_id, user, db)

    res = await db.execute(
        select(VerificationJob)
        .where(VerificationJob.certificate_id == cert.id)
        .order_by(desc(VerificationJob.created_at))
    )
    jobs = res.scalars().all()

    return [
        {
            "id": job.id,
            "status": job.status.value if hasattr(job.status, "value") else str(job.status),
            "current_stage": job.current_stage.value if hasattr(job.current_stage, "value") else str(job.current_stage),
            "progress_percentage": job.progress_percentage,
            "retry_count": job.retry_count,
            "created_at": job.created_at,
            "completed_at": job.completed_at,
        }
        for job in jobs
    ]
