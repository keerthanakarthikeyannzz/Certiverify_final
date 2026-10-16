from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.models import User, Organization, OrganizationMember
from app.schemas.organization_schemas import (
    OrganizationCreateRequest,
    OrganizationResponse,
    OrganizationMemberResponse,
)
from app.api.deps import get_current_verified_user, require_permission
from app.services.tenant_service import slugify
from app.services.audit_service import log_audit_event

router = APIRouter(prefix="/api/v1/organizations", tags=["Organizations"])


@router.post("", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: OrganizationCreateRequest,
    current_user: User = Depends(require_permission("org:manage")),
    db: AsyncSession = Depends(get_db),
):
    """
    Creates a new Organization and assigns current user as Owner.
    """
    slug_val = slugify(payload.slug or payload.name)
    existing = await db.execute(select(Organization).where(Organization.slug == slug_val))
    if existing.scalar_one_or_none():
        slug_val = slugify(f"{payload.name}-{current_user.id[:6]}")

    org = Organization(
        name=payload.name,
        slug=slug_val,
        status="active",
    )
    db.add(org)
    await db.flush()

    member = OrganizationMember(
        organization_id=org.id,
        user_id=current_user.id,
        role="owner",
    )
    db.add(member)

    # Set as user's current organization
    current_user.organization_id = org.id
    await db.commit()
    await db.refresh(org)

    await log_audit_event(
        db,
        action="org:create",
        entity_type="organization",
        actor_user_id=current_user.id,
        organization_id=org.id,
        entity_id=org.id,
        metadata_json={"name": org.name, "slug": org.slug},
    )

    return org


@router.get("/me", response_model=OrganizationResponse)
async def get_my_organization(
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieves the current authenticated user's organization details.
    """
    if not current_user.organization_id:
        raise HTTPException(status_code=404, detail="No organization associated with user")

    result = await db.execute(select(Organization).where(Organization.id == current_user.organization_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


@router.get("/me/members", response_model=list[OrganizationMemberResponse])
async def get_organization_members(
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lists members of the current user's organization.
    """
    if not current_user.organization_id:
        raise HTTPException(status_code=404, detail="No organization associated with user")

    result = await db.execute(
        select(OrganizationMember).where(OrganizationMember.organization_id == current_user.organization_id)
    )
    members = result.scalars().all()
    return members
