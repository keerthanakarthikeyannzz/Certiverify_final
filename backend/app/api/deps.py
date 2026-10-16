from fastapi import Depends, HTTPException, status, Request, Query, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.security import OAuth2PasswordBearer

from app.core.security import decode_token
from app.core.permissions import has_permission, Permission
from app.db.database import get_db
from app.models.models import User, UserRole
from app.services.tenant_service import ensure_user_organization

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        raise credentials_exception

    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exception

    # Auto-provision default organization for legacy or newly registered users if missing
    if not user.organization_id:
        await ensure_user_organization(user, db)

    return user


async def get_current_user_flexible(
    request: Request,
    token_param: str | None = Query(None, alias="token"),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 1. API Key Authentication
    api_key_val = x_api_key
    auth_header = request.headers.get("Authorization")
    if not api_key_val and auth_header and auth_header.startswith("Bearer cv_live_"):
        api_key_val = auth_header.split(" ", 1)[1]
    elif not api_key_val and token_param and token_param.startswith("cv_live_"):
        api_key_val = token_param

    if api_key_val:
        from app.services.api_key_service import get_api_key_context
        api_key_obj = await get_api_key_context(request, api_key_val, db)
        # Create a virtual user bound to the API key's organization for tenant isolation
        virtual_user = User(
            id=f"api_key_{api_key_obj.id}",
            email=f"key_{api_key_obj.key_prefix}@api.certiverify.ai",
            full_name=f"API Key ({api_key_obj.name})",
            role=UserRole.ADMIN,
            organization_id=api_key_obj.organization_id,
            is_active=True,
            is_email_verified=True,
        )
        return virtual_user

    # 2. JWT Token Authentication
    token: str | None = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
    elif token_param:
        token = token_param

    if not token:
        raise credentials_exception

    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        raise credentials_exception

    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exception

    if not user.organization_id:
        await ensure_user_organization(user, db)

    return user


async def get_current_verified_user(user: User = Depends(get_current_user)) -> User:
    if not user.is_email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Please verify your email before continuing.",
        )
    return user


async def get_current_verified_user_flexible(
    user: User = Depends(get_current_user_flexible),
) -> User:
    if not user.is_email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Please verify your email before continuing.",
        )
    return user


def require_role(*allowed_roles: UserRole):
    async def role_checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return user
    return role_checker


def require_permission(permission: str | Permission):
    """
    FastAPI dependency factory to enforce granular permissions.
    """
    perm_str = permission.value if isinstance(permission, Permission) else permission

    async def permission_checker(user: User = Depends(get_current_user)) -> User:
        role_str = user.role.value if hasattr(user.role, "value") else str(user.role)
        if not has_permission(role_str, perm_str):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: Required permission '{perm_str}'",
            )
        return user

    return permission_checker


def verify_tenant_access(
    user: User,
    resource_org_id: str | None,
    resource_owner_id: str | None = None,
) -> bool:
    """
    Validates tenant multi-tenancy isolation and resource ownership.
    Returns True if user has access to resource, else raises HTTP 403.
    """
    role_str = str(user.role.value if hasattr(user.role, "value") else user.role).lower()
    if "admin" in role_str:
        return True

    # If the user is the direct resource owner, access is granted
    if resource_owner_id and str(resource_owner_id) == str(user.id):
        return True

    # Individual students can ONLY access resources they own
    if role_str == "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You do not own this certificate.",
        )

    # Organization staff / verifiers can access resources within their own organization
    if resource_org_id and user.organization_id and str(resource_org_id) == str(user.organization_id):
        return True

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access denied: Resource belongs to another organization",
    )

