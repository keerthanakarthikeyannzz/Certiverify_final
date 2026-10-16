from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.models import User, WebhookEndpoint, WebhookDelivery
from app.api.deps import get_current_verified_user, verify_tenant_access
from app.schemas.webhook_schemas import (
    WebhookCreateRequest, WebhookUpdateRequest, WebhookResponse, WebhookDeliveryResponse
)
from app.services.webhook_service import (
    create_webhook_endpoint, validate_webhook_url, execute_delivery_attempt, generate_webhook_secret
)
from app.services.audit_service import log_audit_event

router = APIRouter(prefix="/api/v1/webhooks", tags=["Webhooks"])


@router.post("", response_model=WebhookResponse, status_code=status.HTTP_201_CREATED)
async def register_webhook(
    req: WebhookCreateRequest,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Registers a new webhook endpoint for the user's organization.
    Returns the HMAC secret ONCE upon creation.
    """
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User does not belong to an active organization.",
        )

    raw_secret, endpoint = await create_webhook_endpoint(
        db=db,
        organization_id=current_user.organization_id,
        endpoint_url=req.endpoint_url,
        subscribed_events=req.subscribed_events,
        actor_user_id=current_user.id,
    )

    return WebhookResponse(
        id=endpoint.id,
        organization_id=endpoint.organization_id,
        endpoint_url=endpoint.endpoint_url,
        subscribed_events=endpoint.subscribed_events or [],
        active=endpoint.active,
        created_at=endpoint.created_at,
        updated_at=endpoint.updated_at,
        secret=raw_secret,
    )


@router.get("", response_model=List[WebhookResponse])
async def list_webhooks(
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lists all active and inactive webhook endpoints for the current organization.
    Secrets are NOT returned in list view for security.
    """
    if not current_user.organization_id:
        return []

    result = await db.execute(
        select(WebhookEndpoint)
        .where(WebhookEndpoint.organization_id == current_user.organization_id)
        .order_by(WebhookEndpoint.created_at.desc())
    )
    endpoints = result.scalars().all()

    return [
        WebhookResponse(
            id=ep.id,
            organization_id=ep.organization_id,
            endpoint_url=ep.endpoint_url,
            subscribed_events=ep.subscribed_events or [],
            active=ep.active,
            created_at=ep.created_at,
            updated_at=ep.updated_at,
            secret=None,
        )
        for ep in endpoints
    ]


@router.get("/{webhook_id}", response_model=WebhookResponse)
async def get_webhook_details(
    webhook_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieves details for a specific webhook endpoint.
    Secret is NOT returned. Enforces tenant isolation.
    """
    result = await db.execute(select(WebhookEndpoint).where(WebhookEndpoint.id == webhook_id))
    ep = result.scalar_one_or_none()

    if not ep:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook endpoint not found.")

    verify_tenant_access(current_user, ep.organization_id)

    return WebhookResponse(
        id=ep.id,
        organization_id=ep.organization_id,
        endpoint_url=ep.endpoint_url,
        subscribed_events=ep.subscribed_events or [],
        active=ep.active,
        created_at=ep.created_at,
        updated_at=ep.updated_at,
        secret=None,
    )


@router.put("/{webhook_id}", response_model=WebhookResponse)
async def update_webhook_endpoint(
    webhook_id: str,
    req: WebhookUpdateRequest,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Updates a webhook endpoint URL, subscribed events, or active status.
    Enforces tenant isolation.
    """
    result = await db.execute(select(WebhookEndpoint).where(WebhookEndpoint.id == webhook_id))
    ep = result.scalar_one_or_none()

    if not ep:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook endpoint not found.")

    verify_tenant_access(current_user, ep.organization_id)

    if req.endpoint_url is not None:
        if not validate_webhook_url(req.endpoint_url):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or unsafe webhook target URL.",
            )
        ep.endpoint_url = req.endpoint_url

    if req.subscribed_events is not None:
        ep.subscribed_events = req.subscribed_events

    if req.active is not None:
        ep.active = req.active

    ep.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(ep)

    await log_audit_event(
        db,
        action="webhook:updated",
        entity_type="webhook_endpoint",
        actor_user_id=current_user.id,
        organization_id=current_user.organization_id,
        entity_id=webhook_id,
        metadata_json={
            "endpoint_url": ep.endpoint_url,
            "subscribed_events": ep.subscribed_events,
            "active": ep.active,
        },
    )

    return WebhookResponse(
        id=ep.id,
        organization_id=ep.organization_id,
        endpoint_url=ep.endpoint_url,
        subscribed_events=ep.subscribed_events or [],
        active=ep.active,
        created_at=ep.created_at,
        updated_at=ep.updated_at,
        secret=None,
    )


@router.delete("/{webhook_id}", status_code=status.HTTP_200_OK)
async def delete_webhook_endpoint(
    webhook_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Deletes a webhook endpoint.
    Enforces tenant isolation.
    """
    result = await db.execute(select(WebhookEndpoint).where(WebhookEndpoint.id == webhook_id))
    ep = result.scalar_one_or_none()

    if not ep:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook endpoint not found.")

    verify_tenant_access(current_user, ep.organization_id)

    await db.delete(ep)
    await db.commit()

    await log_audit_event(
        db,
        action="webhook:deleted",
        entity_type="webhook_endpoint",
        actor_user_id=current_user.id,
        organization_id=current_user.organization_id,
        entity_id=webhook_id,
        metadata_json={"endpoint_url": ep.endpoint_url},
    )

    return {"message": "Webhook endpoint deleted successfully.", "webhook_id": webhook_id}


@router.post("/{webhook_id}/test-delivery", response_model=WebhookDeliveryResponse)
async def test_webhook_delivery(
    webhook_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Triggers a test payload delivery to the specified webhook endpoint.
    """
    result = await db.execute(select(WebhookEndpoint).where(WebhookEndpoint.id == webhook_id))
    ep = result.scalar_one_or_none()

    if not ep:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook endpoint not found.")

    verify_tenant_access(current_user, ep.organization_id)

    test_payload = {
        "event": "ping",
        "message": "CertiVerify webhook test delivery",
        "timestamp": datetime.utcnow().isoformat(),
        "organization_id": ep.organization_id,
    }

    delivery = await execute_delivery_attempt(
        db=db,
        endpoint=ep,
        event_type="test.ping",
        payload=test_payload,
        secret=ep.secret_hash,  # secret or secret hash used for signature
    )

    return WebhookDeliveryResponse(
        id=delivery.id,
        webhook_endpoint_id=delivery.webhook_endpoint_id,
        event_type=delivery.event_type,
        payload=delivery.payload,
        status=delivery.status,
        attempt_count=delivery.attempt_count,
        response_status=delivery.response_status,
        response_body=delivery.response_body,
        next_retry_at=delivery.next_retry_at,
        created_at=delivery.created_at,
        delivered_at=delivery.delivered_at,
    )


@router.get("/{webhook_id}/deliveries", response_model=List[WebhookDeliveryResponse])
async def list_webhook_deliveries(
    webhook_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lists historical webhook delivery attempts for an endpoint.
    """
    result = await db.execute(select(WebhookEndpoint).where(WebhookEndpoint.id == webhook_id))
    ep = result.scalar_one_or_none()

    if not ep:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook endpoint not found.")

    verify_tenant_access(current_user, ep.organization_id)

    del_res = await db.execute(
        select(WebhookDelivery)
        .where(WebhookDelivery.webhook_endpoint_id == webhook_id)
        .order_by(WebhookDelivery.created_at.desc())
    )
    deliveries = del_res.scalars().all()

    return [
        WebhookDeliveryResponse(
            id=d.id,
            webhook_endpoint_id=d.webhook_endpoint_id,
            event_type=d.event_type,
            payload=d.payload,
            status=d.status,
            attempt_count=d.attempt_count,
            response_status=d.response_status,
            response_body=d.response_body,
            next_retry_at=d.next_retry_at,
            created_at=d.created_at,
            delivered_at=d.delivered_at,
        )
        for d in deliveries
    ]
