import logging
from typing import Any
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import AuditLog

logger = logging.getLogger("certiverify.audit")

async def log_audit_event(
    db: AsyncSession,
    action: str,
    entity_type: str,
    actor_user_id: str | None = None,
    organization_id: str | None = None,
    entity_id: str | None = None,
    request: Request | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> AuditLog:
    """
    Persists an enterprise audit log entry in the database.
    """
    if request:
        if not ip_address:
            ip_address = request.client.host if request.client else None
        if not user_agent:
            user_agent = request.headers.get("user-agent")

    audit = AuditLog(
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id else None,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata_json=metadata_json,
    )
    db.add(audit)
    try:
        await db.commit()
        await db.refresh(audit)
    except Exception as e:
        logger.error("Failed to persist audit log: %s", e)
        await db.rollback()
    return audit
