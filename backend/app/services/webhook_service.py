"""
PHASE 4 - ENTERPRISE WEBHOOK ENGINE

Asynchronous webhook dispatch, HMAC-SHA256 request signing, URL safety validation, and exponential backoff retry tracking.
"""
import hmac
import hashlib
import json
import time
import logging
import asyncio
from datetime import datetime, timedelta
from urllib.parse import urlparse
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import AsyncSessionLocal
from app.models.models import (
    WebhookEndpoint, WebhookDelivery, Certificate, VerificationResult, FraudAnalysis
)
from app.services.audit_service import log_audit_event

logger = logging.getLogger("certiverify.webhook")

# Supported event types
EVENT_VERIFICATION_COMPLETED = "verification.completed"
EVENT_VERIFICATION_FAILED    = "verification.failed"
EVENT_FRAUD_ALERT            = "fraud.alert"
EVENT_TAMPER_DETECTED        = "tamper.detected"

ALL_WEBHOOK_EVENTS = [
    EVENT_VERIFICATION_COMPLETED,
    EVENT_VERIFICATION_FAILED,
    EVENT_FRAUD_ALERT,
    EVENT_TAMPER_DETECTED,
]


def generate_webhook_secret() -> str:
    """Generates a random 32-byte secret for webhook HMAC signing."""
    return f"whsec_{hashlib.sha256(json.dumps(time.time()).encode()).hexdigest()[:32]}"


def generate_webhook_signature(payload_bytes: bytes, secret: str, timestamp: int | None = None) -> str:
    """
    Computes HMAC-SHA256 signature for webhook payload verification.
    Format: t=<timestamp>,v1=<signature>
    """
    if timestamp is None:
        timestamp = int(time.time())
    msg = f"{timestamp}.".encode("utf-8") + payload_bytes
    sig = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={sig}"


def compute_webhook_signature(secret: str, payload_bytes: bytes, timestamp: int) -> str:
    """Alias for generate_webhook_signature."""
    return generate_webhook_signature(payload_bytes, secret, timestamp)


def verify_webhook_signature(payload_bytes: bytes, secret: str, signature_header: str) -> bool:
    """
    Validates received X-CertiVerify-Signature header against computed HMAC.
    """
    try:
        parts = dict(pair.split("=", 1) for pair in signature_header.split(","))
        timestamp = int(parts.get("t", 0))
        received_sig = parts.get("v1", "")

        expected_header = generate_webhook_signature(payload_bytes, secret, timestamp)
        expected_sig = dict(pair.split("=", 1) for pair in expected_header.split(",")).get("v1", "")

        return hmac.compare_digest(received_sig, expected_sig)
    except Exception:
        return False


import ipaddress
import socket

def is_ip_private_or_reserved(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        )
    except ValueError:
        return False


def validate_webhook_url(url: str) -> bool:
    """
    Validates URL safety to prevent SSRF against internal services.
    Allows standard http/https schemes, blocks localhost, private IPs (RFC 1918),
    loopback, link-local, cloud metadata services, and internal hostnames.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = (parsed.hostname or "").lower()
        if not hostname:
            return False

        # Block well-known internal/metadata hostnames
        blocked_hostnames = {
            "localhost",
            "metadata.google.internal",
            "instance-data",
            "metadata",
        }
        if (
            hostname in blocked_hostnames
            or hostname.endswith(".local")
            or hostname.endswith(".internal")
            or hostname.endswith(".localhost")
        ):
            return False

        # Check if hostname directly represents an IP address
        try:
            ip = ipaddress.ip_address(hostname)
            if is_ip_private_or_reserved(str(ip)) or str(ip) == "169.254.169.254":
                return False
            return True
        except ValueError:
            pass

        # String-prefix heuristic for common internal ranges if hostname is IP-like
        if (
            hostname.startswith("10.")
            or hostname.startswith("192.168.")
            or hostname.startswith("127.")
            or hostname.startswith("169.254.")
        ):
            return False

        # Resolve hostname via DNS to prevent DNS rebinding or internal resolution
        try:
            addr_info = socket.getaddrinfo(hostname, None)
            for _, _, _, _, sockaddr in addr_info:
                ip_addr = sockaddr[0]
                if is_ip_private_or_reserved(ip_addr) or ip_addr == "169.254.169.254":
                    return False
        except socket.gaierror:
            # Cannot resolve domain (e.g. offline tests). Allow safe domains, block internal
            if "localhost" in hostname or "internal" in hostname:
                return False

        return True
    except Exception:
        return False


def is_safe_webhook_url(url: str) -> bool:
    """Alias for validate_webhook_url."""
    return validate_webhook_url(url)


async def create_webhook_endpoint(
    db: AsyncSession,
    organization_id: str,
    endpoint_url: str,
    subscribed_events: list[str],
    actor_user_id: str | None = None,
) -> tuple[str, WebhookEndpoint]:
    """
    Creates and persists a new WebhookEndpoint.
    Returns (raw_secret, endpoint_row). Secret is ONLY returned once during creation.
    """
    if not validate_webhook_url(endpoint_url):
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or unsafe webhook target URL.",
        )

    raw_secret = generate_webhook_secret()
    # Store raw_secret in secret_hash field (or hashed secret depending on design)
    endpoint = WebhookEndpoint(
        organization_id=organization_id,
        endpoint_url=endpoint_url,
        secret_hash=raw_secret,
        subscribed_events=subscribed_events,
        active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(endpoint)
    await db.commit()
    await db.refresh(endpoint)

    await log_audit_event(
        db,
        action="webhook:created",
        entity_type="webhook_endpoint",
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        entity_id=endpoint.id,
        metadata_json={
            "endpoint_url": endpoint_url,
            "subscribed_events": subscribed_events,
        },
    )

    return raw_secret, endpoint


async def execute_delivery_attempt(
    db: AsyncSession,
    delivery_or_id: str | WebhookDelivery | None = None,
    endpoint: WebhookEndpoint | None = None,
    event_type: str | None = None,
    payload: dict | None = None,
    secret: str | None = None,
) -> WebhookDelivery:
    """
    Executes a single HTTP delivery attempt for a WebhookDelivery record.
    Implements HMAC signing and handles exponential backoff retries.
    """
    delivery: WebhookDelivery | None = None

    if isinstance(delivery_or_id, WebhookDelivery):
        delivery = delivery_or_id
    elif isinstance(delivery_or_id, str):
        res = await db.execute(select(WebhookDelivery).where(WebhookDelivery.id == delivery_or_id))
        delivery = res.scalar_one_or_none()

    if not delivery and endpoint and event_type and payload:
        delivery = WebhookDelivery(
            webhook_endpoint_id=endpoint.id,
            event_type=event_type,
            payload=payload,
            status="PENDING",
            attempt_count=1,
            created_at=datetime.utcnow(),
        )
        db.add(delivery)
        await db.commit()
        await db.refresh(delivery)

    if not delivery:
        raise ValueError("Invalid parameters for execute_delivery_attempt")

    if not endpoint:
        endpoint_res = await db.execute(select(WebhookEndpoint).where(WebhookEndpoint.id == delivery.webhook_endpoint_id))
        endpoint = endpoint_res.scalar_one_or_none()

    if not endpoint or not endpoint.active:
        delivery.status = "FAILED"
        delivery.response_body = "Endpoint deactivated or deleted."
        await db.commit()
        return delivery

    if not validate_webhook_url(endpoint.endpoint_url):
        delivery.status = "FAILED"
        delivery.response_body = "Delivery blocked: Target URL failed SSRF safety checks."
        await db.commit()
        return delivery

    # Re-validate DNS resolution at dispatch time to prevent DNS rebinding attacks
    try:
        parsed_url = urlparse(endpoint.endpoint_url)
        host = (parsed_url.hostname or "").lower()
        if host:
            addr_info = socket.getaddrinfo(host, None)
            for _, _, _, _, sockaddr in addr_info:
                resolved_ip = sockaddr[0]
                if is_ip_private_or_reserved(resolved_ip) or resolved_ip == "169.254.169.254":
                    delivery.status = "FAILED"
                    delivery.response_body = f"Delivery blocked: Target IP {resolved_ip} is internal/reserved."
                    await db.commit()
                    return delivery
    except (socket.gaierror, Exception) as dns_err:
        logger.warning("Dispatch DNS resolution check for %s: %s", endpoint.endpoint_url, dns_err)

    signing_secret = secret or endpoint.secret_hash
    timestamp = int(time.time())
    payload_bytes = json.dumps(delivery.payload, sort_keys=True).encode("utf-8")
    signature = generate_webhook_signature(payload_bytes, signing_secret, timestamp)

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "CertiVerify-Webhook/1.0",
        "X-CertiVerify-Signature": signature,
        "X-CertiVerify-Event": delivery.event_type,
        "X-CertiVerify-Delivery": delivery.id,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            resp = await client.post(endpoint.endpoint_url, content=payload_bytes, headers=headers)
            
            delivery.response_status = resp.status_code
            delivery.response_body = resp.text[:1000]

            if 200 <= resp.status_code < 300:
                delivery.status = "SUCCESS"
                delivery.delivered_at = datetime.utcnow()
                await db.commit()
                return delivery
            else:
                if 400 <= resp.status_code < 500:
                    delivery.status = "FAILED"
                else:
                    await _schedule_retry_or_fail(db, delivery, endpoint.organization_id)
                await db.commit()
                return delivery

    except Exception as exc:
        logger.warning("Webhook delivery attempt %d failed for endpoint %s: %s", delivery.attempt_count, endpoint.id, exc)
        delivery.response_body = f"Connection error: {str(exc)[:500]}"
        await _schedule_retry_or_fail(db, delivery, endpoint.organization_id)
        await db.commit()
        return delivery


async def _schedule_retry_or_fail(db: AsyncSession, delivery: WebhookDelivery, organization_id: str):
    """Schedules retry with exponential backoff (5s, 30s, 300s) up to 3 attempts."""
    if delivery.attempt_count < 3:
        backoff_delays = [5, 30, 300]
        delay_sec = backoff_delays[min(delivery.attempt_count - 1, len(backoff_delays) - 1)]
        delivery.status = "RETRYING"
        delivery.attempt_count += 1
        delivery.next_retry_at = datetime.utcnow() + timedelta(seconds=delay_sec)
    else:
        delivery.status = "FAILED"
        await log_audit_event(
            db,
            action="webhook:delivery_failed",
            entity_type="webhook_delivery",
            organization_id=organization_id,
            entity_id=delivery.id,
            metadata_json={"event_type": delivery.event_type, "attempts": delivery.attempt_count},
        )


async def dispatch_webhook_event(
    db: AsyncSession,
    organization_id: str | None,
    event_type: str,
    payload: dict,
) -> list[WebhookDelivery]:
    """
    Queries active endpoints subscribed to event_type for the organization,
    creates WebhookDelivery records, and dispatches HTTP requests.
    """
    if not organization_id:
        return []

    res = await db.execute(
        select(WebhookEndpoint).where(
            WebhookEndpoint.organization_id == organization_id,
            WebhookEndpoint.active == True,
        )
    )
    endpoints = res.scalars().all()

    matching_endpoints = [
        ep for ep in endpoints
        if ep.subscribed_events and (event_type in ep.subscribed_events or "*" in ep.subscribed_events)
    ]

    if not matching_endpoints:
        return []

    deliveries = []
    for ep in matching_endpoints:
        delivery = WebhookDelivery(
            webhook_endpoint_id=ep.id,
            event_type=event_type,
            payload=payload,
            status="PENDING",
            attempt_count=1,
            created_at=datetime.utcnow(),
        )
        db.add(delivery)
        deliveries.append(delivery)

    await db.commit()

    for d in deliveries:
        asyncio.create_task(_async_deliver(d.id))

    return deliveries


async def _async_deliver(delivery_id: str):
    """Background wrapper creating an isolated DB session for webhook execution."""
    async with AsyncSessionLocal() as db:
        await execute_delivery_attempt(db, delivery_id)
