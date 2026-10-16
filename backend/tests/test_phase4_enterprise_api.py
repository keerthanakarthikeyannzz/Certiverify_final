import uuid
# pyrefly: ignore [missing-import]
import pytest
from datetime import datetime, timedelta
from app.db.database import AsyncSessionLocal
from app.models.models import User, Organization, UserRole, ApiKey, WebhookEndpoint, WebhookDelivery, AuditLog
from app.services.api_key_service import (
    create_api_key, hash_api_key, get_api_key_context, verify_api_key_permission, rate_limiter
)
from app.services.webhook_service import (
    create_webhook_endpoint, generate_webhook_signature, verify_webhook_signature,
    validate_webhook_url, execute_delivery_attempt, dispatch_webhook_event
)
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_api_key_creation_and_hashing():
    """Verifies API key generation, raw key output format, and secure SHA-256 hashing."""
    async with AsyncSessionLocal() as db:
        org_id = str(uuid.uuid4())
        org = Organization(id=org_id, name="Org A", slug=f"org-a-{uuid.uuid4().hex[:8]}")
        db.add(org)
        await db.commit()

        raw_key, api_key_row = await create_api_key(
            db=db,
            organization_id=org_id,
            name="CI Test Key",
            permissions=["certificate:read", "certificate:upload"],
            rate_limit=50,
        )

        assert raw_key.startswith("cv_live_")
        assert api_key_row.key_prefix in raw_key
        assert api_key_row.hashed_key == hash_api_key(raw_key)
        assert api_key_row.hashed_key != raw_key  # Never store raw key
        assert api_key_row.permissions == ["certificate:read", "certificate:upload"]
        assert api_key_row.status == "active"
        assert api_key_row.rate_limit == 50

        # Check audit log
        audit = await db.execute(
            AuditLog.__table__.select().where(AuditLog.action == "api_key:created")
        )
        assert audit.first() is not None


@pytest.mark.asyncio
async def test_api_key_permission_scope_checking():
    """Verifies scope checking for restricted and allowed permissions."""
    api_key = ApiKey(
        id=str(uuid.uuid4()),
        organization_id=str(uuid.uuid4()),
        permissions=["certificate:read", "evidence:read"],
    )

    # Allowed scopes
    verify_api_key_permission(api_key, "certificate:read")
    verify_api_key_permission(api_key, "evidence:read")

    # Forbidden scope
    with pytest.raises(HTTPException) as exc_info:
        verify_api_key_permission(api_key, "certificate:delete")
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_api_key_expiration_and_revocation():
    """Verifies expired and revoked API keys are rejected."""
    async with AsyncSessionLocal() as db:
        org_id = str(uuid.uuid4())
        org = Organization(id=org_id, name="Org B", slug=f"org-b-{uuid.uuid4().hex[:8]}")
        db.add(org)
        await db.commit()

        # Expired Key
        raw_exp, exp_key = await create_api_key(
            db=db,
            organization_id=org_id,
            name="Expired Key",
            permissions=["*"],
            expires_at=datetime.utcnow() - timedelta(days=1),
        )

        # Revoked Key
        raw_rev, rev_key = await create_api_key(
            db=db,
            organization_id=org_id,
            name="Revoked Key",
            permissions=["*"],
        )
        rev_key.status = "revoked"
        await db.commit()

        # Verify Expired raises 401
        class MockRequest:
            state = type("State", (), {})()

        with pytest.raises(HTTPException) as exc1:
            await get_api_key_context(MockRequest(), x_api_key=raw_exp, db=db)
        assert exc1.value.status_code == 401

        # Verify Revoked raises 401
        with pytest.raises(HTTPException) as exc2:
            await get_api_key_context(MockRequest(), x_api_key=raw_rev, db=db)
        assert exc2.value.status_code == 401


@pytest.mark.asyncio
async def test_api_key_rate_limiting():
    """Verifies rate limiting triggers HTTP 429 when threshold exceeded."""
    key_id = f"test_key_{uuid.uuid4()}"
    limit = 3

    for i in range(3):
        allowed, lim, remaining, _ = rate_limiter.check_rate_limit(key_id, limit)
        assert allowed is True

    # 4th attempt should be blocked
    allowed, lim, remaining, reset = rate_limiter.check_rate_limit(key_id, limit)
    assert allowed is False
    assert remaining == 0


@pytest.mark.asyncio
async def test_webhook_creation_and_hmac_signature():
    """Verifies HMAC-SHA256 signature calculation and validation."""
    async with AsyncSessionLocal() as db:
        org_id = str(uuid.uuid4())
        org = Organization(id=org_id, name="Org Webhook", slug=f"org-wh-{uuid.uuid4().hex[:8]}")
        db.add(org)
        await db.commit()

        raw_secret, ep = await create_webhook_endpoint(
            db=db,
            organization_id=org_id,
            endpoint_url="https://example.com/webhook",
            subscribed_events=["verification.completed", "fraud.alert"],
        )

        assert raw_secret.startswith("whsec_")
        payload_bytes = b'{"event":"verification.completed","job_id":"123"}'

        sig = generate_webhook_signature(payload_bytes, raw_secret)
        assert verify_webhook_signature(payload_bytes, raw_secret, sig) is True
        assert verify_webhook_signature(payload_bytes, raw_secret, "invalid_sig") is False


@pytest.mark.asyncio
async def test_webhook_url_safety_validation():
    """Verifies safety checks preventing SSRF attacks on localhost / internal IPs."""
    assert validate_webhook_url("https://api.externalpartner.com/webhooks") is True
    assert validate_webhook_url("http://localhost:8000/webhook") is False
    assert validate_webhook_url("http://127.0.0.1/webhook") is False
    assert validate_webhook_url("http://169.254.169.254/latest/meta-data") is False
    assert validate_webhook_url("ftp://example.com/webhook") is False


@pytest.mark.asyncio
async def test_webhook_event_dispatch_and_tenant_isolation():
    """Verifies webhook events are dispatched only to endpoints belonging to the target organization."""
    async with AsyncSessionLocal() as db:
        org_a = str(uuid.uuid4())
        org_b = str(uuid.uuid4())

        # Endpoint for Org A
        _, ep_a = await create_webhook_endpoint(
            db=db,
            organization_id=org_a,
            endpoint_url="https://org-a.com/webhook",
            subscribed_events=["verification.completed"],
        )

        # Endpoint for Org B
        _, ep_b = await create_webhook_endpoint(
            db=db,
            organization_id=org_b,
            endpoint_url="https://org-b.com/webhook",
            subscribed_events=["verification.completed"],
        )

        # Dispatch event for Org A
        deliveries_a = await dispatch_webhook_event(
            db=db,
            organization_id=org_a,
            event_type="verification.completed",
            payload={"job_id": "job-100", "status": "COMPLETED"},
        )

        assert len(deliveries_a) == 1
        assert deliveries_a[0].webhook_endpoint_id == ep_a.id
