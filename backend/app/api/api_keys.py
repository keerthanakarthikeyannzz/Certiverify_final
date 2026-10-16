from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.models import User, ApiKey
from app.api.deps import get_current_verified_user, verify_tenant_access, require_permission
from app.schemas.api_key_schemas import ApiKeyCreateRequest, ApiKeyCreateResponse, ApiKeyResponse
from app.services.api_key_service import create_api_key
from app.services.audit_service import log_audit_event

router = APIRouter(prefix="/api/v1/api-keys", tags=["API Keys"])


@router.post("", response_model=ApiKeyCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_new_api_key(
    req: ApiKeyCreateRequest,
    current_user: User = Depends(require_permission("api_key:write")),
    db: AsyncSession = Depends(get_db),
):
    """
    Generates a new enterprise API key for the authenticated user's organization.
    The raw key is returned ONLY once in the response.
    """
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User does not belong to an active organization.",
        )

    raw_key, api_key_row = await create_api_key(
        db=db,
        organization_id=current_user.organization_id,
        name=req.name,
        permissions=req.permissions,
        rate_limit=req.rate_limit,
        expires_at=req.expires_at,
        actor_user_id=current_user.id,
    )

    return ApiKeyCreateResponse(
        id=api_key_row.id,
        organization_id=api_key_row.organization_id,
        key_prefix=api_key_row.key_prefix,
        raw_key=raw_key,
        name=api_key_row.name,
        permissions=api_key_row.permissions or [],
        status=api_key_row.status,
        rate_limit=api_key_row.rate_limit,
        expires_at=api_key_row.expires_at,
        created_at=api_key_row.created_at,
    )


@router.get("", response_model=List[ApiKeyResponse])
async def list_api_keys(
    current_user: User = Depends(require_permission("api_key:write")),
    db: AsyncSession = Depends(get_db),
):
    """
    Lists all API keys created for the current user's organization.
    Raw keys are never returned.
    """
    if not current_user.organization_id:
        return []

    result = await db.execute(
        select(ApiKey)
        .where(ApiKey.organization_id == current_user.organization_id)
        .order_by(ApiKey.created_at.desc())
    )
    keys = result.scalars().all()

    return [
        ApiKeyResponse(
            id=k.id,
            organization_id=k.organization_id,
            key_prefix=k.key_prefix,
            name=k.name,
            permissions=k.permissions or [],
            status=k.status,
            rate_limit=k.rate_limit,
            expires_at=k.expires_at,
            last_used_at=k.last_used_at,
            created_at=k.created_at,
            revoked_at=k.revoked_at,
        )
        for k in keys
    ]


@router.delete("/{key_id}", status_code=status.HTTP_200_OK)
async def revoke_api_key(
    key_id: str,
    current_user: User = Depends(require_permission("api_key:write")),
    db: AsyncSession = Depends(get_db),
):
    """
    Revokes an existing API key.
    Enforces tenant isolation.
    """
    result = await db.execute(select(ApiKey).where(ApiKey.id == key_id))
    api_key_row = result.scalar_one_or_none()

    if not api_key_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API Key not found.",
        )

    verify_tenant_access(current_user, api_key_row.organization_id)

    if api_key_row.status == "revoked":
        return {"message": "API key is already revoked.", "key_id": key_id}

    api_key_row.status = "revoked"
    api_key_row.revoked_at = datetime.utcnow()
    await db.commit()

    await log_audit_event(
        db,
        action="api_key:revoked",
        entity_type="api_key",
        actor_user_id=current_user.id,
        organization_id=current_user.organization_id,
        entity_id=key_id,
        metadata_json={"key_prefix": api_key_row.key_prefix, "name": api_key_row.name},
    )

    return {"message": "API key successfully revoked.", "key_id": key_id}
