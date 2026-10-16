import re
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import User, Organization, OrganizationMember

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text or "org"

async def ensure_user_organization(user: User, db: AsyncSession) -> Organization:
    """
    Ensure the user has an active Organization assigned.
    If user.organization_id is None, create/assign a default organization for them.
    This preserves 100% backward compatibility for existing users.
    """
    if user.organization_id:
        result = await db.execute(select(Organization).where(Organization.id == user.organization_id))
        org = result.scalar_one_or_none()
        if org:
            return org

    # Check if a personal organization slug already exists
    base_slug = slugify(f"{user.full_name}-{user.id[:8]}")
    result = await db.execute(select(Organization).where(Organization.slug == base_slug))
    existing_org = result.scalar_one_or_none()

    if existing_org:
        user.organization_id = existing_org.id
        await db.commit()
        await db.refresh(user)
        return existing_org

    # Create new personal default Organization for user
    org_name = f"{user.full_name}'s Organization"
    org = Organization(
        name=org_name,
        slug=base_slug,
        status="active"
    )
    db.add(org)
    await db.flush()

    member = OrganizationMember(
        organization_id=org.id,
        user_id=user.id,
        role="owner"
    )
    db.add(member)

    user.organization_id = org.id
    await db.commit()
    await db.refresh(user)
    await db.refresh(org)
    return org
