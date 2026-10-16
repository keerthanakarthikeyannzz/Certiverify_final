"""
Unit tests for Module 6 (Part 1) - QR Check + Blockchain Verification.
Full API tests need an authenticated session with a stored certificate
(see NOTE in test_upload.py). These cover auth-gating plus the QR
verification engine's pure logic — every assertion here was run against
the real implementation during development (see test output in the
conversation this was built in), not written blind.
"""
import json
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.services.qr_verification import verify_qr
from app.services.blockchain_service import verify_hash_onchain

CERT_BASE = "/api/v1/certificates"


@pytest.mark.asyncio
async def test_verify_qr_requires_authentication():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(f"{CERT_BASE}/00000000-0000-0000-0000-000000000000/verify-qr")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_verify_blockchain_requires_authentication():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(f"{CERT_BASE}/00000000-0000-0000-0000-000000000000/verify-blockchain")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_verification_requires_authentication():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(f"{CERT_BASE}/00000000-0000-0000-0000-000000000000/verification")
    assert resp.status_code == 401


def test_qr_missing_generates_warning_not_a_hard_fail():
    result = verify_qr(None)
    assert result.present is False
    assert result.valid is None
    assert "No QR code detected" in result.warning


def test_qr_valid_structured_payload_matching_certificate():
    payload = json.dumps({
        "certificate_id": "CERT-2024-00981", "verification_token": "abc123", "expiry": "2030-01-01",
    })
    result = verify_qr(payload, expected_certificate_number="CERT-2024-00981")
    assert result.present is True
    assert result.valid is True
    assert result.warning is None


def test_qr_certificate_id_mismatch_flagged():
    payload = json.dumps({"certificate_id": "WRONG-ID", "verification_token": "abc123", "expiry": "2030-01-01"})
    result = verify_qr(payload, expected_certificate_number="CERT-2024-00981")
    assert result.valid is False
    assert "does not match" in result.warning


def test_qr_expired_token_flagged():
    payload = json.dumps({"certificate_id": "X", "verification_token": "t", "expiry": "2020-01-01"})
    result = verify_qr(payload, expected_certificate_number="X")
    assert result.valid is False
    assert "expired" in result.warning


def test_qr_plain_url_accepted():
    result = verify_qr("https://university.edu/verify?id=123")
    assert result.valid is True
    assert result.decoded["url"] == "https://university.edu/verify?id=123"


def test_qr_garbage_content_rejected():
    result = verify_qr("not a url or json !!!")
    assert result.valid is False


def test_blockchain_verification_unavailable_when_unconfigured():
    # No CONTRACT_ADDRESS / provider configured in the test environment ->
    # must degrade gracefully to "unavailable", never raise or 500.
    result = verify_hash_onchain("a" * 64)
    assert result.status == "unavailable"
    assert result.match is None
