"""
PHASE 4 - ENTERPRISE API KEY SERVICE

Secure key generation, SHA-256 hashing, rate limiting, and permission scope validation.
"""
import hashlib
import secrets
import time
import logging
from datetime import datetime
from collections import defaultdict
from fastapi import Header, Depends, HTTPException, status, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.models import ApiKey, Organization
from app.services.audit_service import log_audit_event

logger = logging.getLogger("certiverify.api_key")

# ---------------------------------------------------------------------------
# IN-MEMORY RATE LIMITER (Abstraction over Redis)
# ---------------------------------------------------------------------------
class RateLimiterMemory:
    """
    In-memory fixed-window rate limiter per API key / Organization.
    Designed with a clean interface so Redis can be swapped in seamlessly.
    """
    def __init__(self):
        # key -> (window_start_timestamp, request_count)
        self._store: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))

    def check_rate_limit(self, key_id: str, limit_per_min: int) -> tuple[bool, int, int, int]:
        """
        Returns (is_allowed, limit, remaining, reset_seconds).
        """
        now = int(time.time())
        window_start = now - (now % 60)
        reset_time = window_start + 60 - now

        current_window, count = self._store[key_id]
        if current_window != window_start:
            count = 0
            current_window = window_start

        if count >= limit_per_min:
            remaining = 0
            return False, limit_per_min, remaining, reset_time

        count += 1
        self._store[key_id] = (window_start, count)
        remaining = limit_per_min - count
        return True, limit_per_min, remaining, reset_time

rate_limiter = RateLimiterMemory()


# ---------------------------------------------------------------------------
# SECURE API KEY GENERATION & VERIFICATION
# ---------------------------------------------------------------------------

def hash_api_key(raw_key: str) -> str:
    """Computes SHA-256 hash of raw API key for secure storage."""
    return hashlib.sha256(raw_key.strip().encode("utf-8")).hexdigest()


def generate_raw_api_key() -> tuple[str, str, str]:
    """
    Generates a secure API key string.
    Returns (raw_key, key_prefix, hashed_key).
    Raw key format: cv_live_<prefix>_<secret>
    """
    prefix_rnd = secrets.token_hex(4)             # 8 hex chars
    secret_rnd = secrets.token_urlsafe(24)           # 32 chars
    key_prefix = f"cv_live_{prefix_rnd}"
    raw_key = f"{key_prefix}_{secret_rnd}"
    hashed_key = hash_api_key(raw_key)
    return raw_key, key_prefix, hashed_key


async def create_api_key(
    db: AsyncSession,
    organization_id: str,
    name: str,
    permissions: list[str],
    rate_limit: int = 100,
    expires_at: datetime | None = None,
    actor_user_id: str | None = None,
) -> tuple[str, ApiKey]:
    """
    Creates and persists a new ApiKey entity.
    Returns (raw_key, api_key_row). Raw key is ONLY shown once during creation.
    """
    raw_key, prefix, hashed_key = generate_raw_api_key()

    api_key_row = ApiKey(
        organization_id=organization_id,
        key_prefix=prefix,
        hashed_key=hashed_key,
        name=name,
        permissions=permissions,
        status="active",
        rate_limit=rate_limit,
        expires_at=expires_at,
        created_at=datetime.utcnow(),
    )
    db.add(api_key_row)
    await db.commit()
    await db.refresh(api_key_row)

    await log_audit_event(
        db,
        action="api_key:created",
        entity_type="api_key",
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        entity_id=api_key_row.id,
        metadata_json={
            "name": name,
            "prefix": prefix,
            "permissions": permissions,
            "rate_limit": rate_limit,
        },
    )

    return raw_key, api_key_row


# ---------------------------------------------------------------------------
# FASTAPI DEPENDENCY - X-API-Key AUTHENTICATION
# ---------------------------------------------------------------------------

async def get_api_key_context(
    request: Request,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> ApiKey:
    """
    FastAPI dependency validating the X-API-Key header.
    Checks hashed key match, active status, expiration, and rate limits.
    Populates response headers with rate limiting telemetry.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required 'X-API-Key' authentication header.",
        )

    hashed = hash_api_key(x_api_key)
    result = await db.execute(select(ApiKey).where(ApiKey.hashed_key == hashed))
    api_key_row = result.scalar_one_or_none()

    if not api_key_row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key supplied.",
        )

    if api_key_row.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"API key is '{api_key_row.status}' and cannot be used.",
        )

    if api_key_row.expires_at and api_key_row.expires_at < datetime.utcnow():
        api_key_row.status = "expired"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key has expired.",
        )

    # Rate limiting check
    allowed, limit, remaining, reset_sec = rate_limiter.check_rate_limit(
        api_key_row.id, api_key_row.rate_limit
    )

    # Attach headers if response available (via request state or middleware)
    request.state.rate_limit = limit
    request.state.rate_remaining = remaining
    request.state.rate_reset = reset_sec

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"API key rate limit of {limit} requests/minute exceeded. Try again in {reset_sec} seconds.",
            headers={
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset_sec),
            },
        )

    # Update last_used_at
    api_key_row.last_used_at = datetime.utcnow()
    await db.commit()

    return api_key_row


def verify_api_key_permission(api_key: ApiKey, required_scope: str):
    """
    Validates that an API key possesses a specific permission scope.
    """
    perms = api_key.permissions or []
    if required_scope not in perms and "*" not in perms and "admin" not in perms:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"API Key permission denied: Key lacks required scope '{required_scope}'.",
        )
