from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.models import User, AuditLog
from app.schemas.audit_schemas import AuditLogResponse
from app.api.deps import require_permission, get_current_verified_user

router = APIRouter(prefix="/api/v1/audit-logs", tags=["Audit Logs"])


@router.get("", response_model=list[AuditLogResponse])
async def list_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_permission("audit:read")),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns audit logs for the authenticated user's organization.
    Requires 'audit:read' permission.
    """
    query = select(AuditLog)
    if current_user.organization_id:
        query = query.where(AuditLog.organization_id == current_user.organization_id)
    else:
        query = query.where(AuditLog.actor_user_id == current_user.id)

    query = query.order_by(AuditLog.timestamp.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    logs = result.scalars().all()
    return logs
