"""
Unit tests for Module 1 - Authentication.
Run with: pytest -v
Tests both development mode (EMAIL_VERIFICATION_REQUIRED=False) and production mode (EMAIL_VERIFICATION_REQUIRED=True).
"""
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.core.config import settings, Settings
from app.db.database import AsyncSessionLocal
from app.models.models import User, OTPCode, OTPPurpose

BASE = "/api/v1/auth"


@pytest.mark.asyncio
async def test_register_new_user_dev_mode():
    """In development mode, newly registered users are active and verified without OTP."""
    test_email = f"test.student.{uuid.uuid4().hex[:8]}@example.com"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(f"{BASE}/register", json={
            "full_name": "Test Student",
            "email": test_email,
            "password": "StrongPass1",
            "role": "student",
        })
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == test_email
    assert body["is_active"] is True
    assert body["is_email_verified"] is True


@pytest.mark.asyncio
async def test_dev_registration_direct_login_flow():
    """Verify registration succeeds and permits immediate login without requiring an email OTP."""
    unique_email = f"direct_login_{uuid.uuid4().hex[:8]}@example.com"
    password = "StrongPass1"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Register
        reg = await ac.post(f"{BASE}/register", json={
            "full_name": "Direct Login Tester",
            "email": unique_email,
            "password": password,
            "role": "student",
        })
        assert reg.status_code == 201
        assert reg.json()["is_email_verified"] is True

        # 2. Confirm no OTPCode was created in database
        async with AsyncSessionLocal() as session:
            user_res = await session.execute(select(User).where(User.email == unique_email))
            user = user_res.scalar_one()
            otp_res = await session.execute(
                select(OTPCode).where(OTPCode.user_id == user.id)
            )
            assert otp_res.scalars().first() is None

        # 3. Direct Login succeeds immediately without OTP
        login_resp = await ac.post(f"{BASE}/login", json={
            "email": unique_email,
            "password": password,
        })
        assert login_resp.status_code == 200
        tokens = login_resp.json()
        assert "access_token" in tokens
        assert "refresh_token" in tokens
        access_token = tokens["access_token"]

        # 4. Access authenticated /me endpoint with generated JWT
        me_resp = await ac.get(f"{BASE}/me", headers={"Authorization": f"Bearer {access_token}"})
        assert me_resp.status_code == 200
        assert me_resp.json()["email"] == unique_email


@pytest.mark.asyncio
async def test_register_duplicate_email_rejected():
    dup_email = f"dup.{uuid.uuid4().hex[:8]}@example.com"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {
            "full_name": "Dup User", "email": dup_email,
            "password": "StrongPass1", "role": "student",
        }
        first = await ac.post(f"{BASE}/register", json=payload)
        second = await ac.post(f"{BASE}/register", json=payload)
    assert first.status_code == 201
    assert second.status_code in (400, 409)


@pytest.mark.asyncio
async def test_weak_password_rejected():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(f"{BASE}/register", json={
            "full_name": "Weak Pw", "email": "weak@example.com",
            "password": "weakpass", "role": "student",
        })
    assert resp.status_code == 422  # fails password_strength validator


@pytest.mark.asyncio
async def test_login_wrong_password():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(f"{BASE}/login", json={
            "email": "nonexistent@example.com", "password": "whatever123",
        })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoints_require_authentication():
    """Protected endpoints must reject unauthenticated requests with 401."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        me_resp = await ac.get(f"{BASE}/me")
        assert me_resp.status_code == 401

        cert_resp = await ac.get("/api/v1/certificates/history")
        assert cert_resp.status_code == 401


def test_production_default_requires_email_verification():
    """Confirm production verification behavior remains enabled by default."""
    prod_settings = Settings(_env_file=None, ENV="production")
    assert prod_settings.EMAIL_VERIFICATION_REQUIRED is True

    dev_settings = Settings(_env_file=None, ENV="development")
    assert dev_settings.EMAIL_VERIFICATION_REQUIRED is False

    prod_override = Settings(_env_file=None, ENV="production", EMAIL_VERIFICATION_REQUIRED=False)
    assert prod_override.EMAIL_VERIFICATION_REQUIRED is False

    dev_override = Settings(_env_file=None, ENV="development", EMAIL_VERIFICATION_REQUIRED=True)
    assert dev_override.EMAIL_VERIFICATION_REQUIRED is True


@pytest.mark.asyncio
async def test_login_blocked_before_email_verification(monkeypatch):
    """When EMAIL_VERIFICATION_REQUIRED=True, unverified accounts cannot sign in."""
    monkeypatch.setattr(settings, "EMAIL_VERIFICATION_REQUIRED", True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        unique_email = f"unverified_{uuid.uuid4().hex[:8]}@example.com"
        reg_resp = await ac.post(f"{BASE}/register", json={
            "full_name": "Unverified", "email": unique_email,
            "password": "StrongPass1", "role": "student",
        })
        assert reg_resp.status_code == 201
        assert reg_resp.json()["is_email_verified"] is False

        resp = await ac.post(f"{BASE}/login", json={
            "email": unique_email, "password": "StrongPass1",
        })
    assert resp.status_code == 403
    assert "not verified" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_verify_login_complete_flow(monkeypatch):
    """Full lifecycle when EMAIL_VERIFICATION_REQUIRED=True: register -> blocked login -> verify-email with OTP -> login."""
    monkeypatch.setattr(settings, "EMAIL_VERIFICATION_REQUIRED", True)
    unique_email = f"flow_user_{uuid.uuid4().hex[:8]}@example.com"
    password = "StrongPass1"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Register
        reg = await ac.post(f"{BASE}/register", json={
            "full_name": "Flow Tester",
            "email": unique_email,
            "password": password,
            "role": "student",
        })
        assert reg.status_code == 201
        assert reg.json()["is_email_verified"] is False

        # 2. Login attempt must fail with 403
        login_fail = await ac.post(f"{BASE}/login", json={"email": unique_email, "password": password})
        assert login_fail.status_code == 403
        assert "not verified" in login_fail.json()["detail"].lower()

        # 3. Verify with wrong OTP fails
        wrong_verify = await ac.post(f"{BASE}/verify-email", json={"email": unique_email, "code": "999999"})
        assert wrong_verify.status_code == 400

        # 4. Fetch actual OTP from database
        async with AsyncSessionLocal() as session:
            user_res = await session.execute(select(User).where(User.email == unique_email))
            user = user_res.scalar_one()
            otp_res = await session.execute(
                select(OTPCode)
                .where(OTPCode.user_id == user.id, OTPCode.purpose == OTPPurpose.EMAIL_VERIFICATION)
                .order_by(OTPCode.created_at.desc())
            )
            otp = otp_res.scalars().first()
            assert otp is not None
            valid_code = otp.code

        # 5. Verify email with correct OTP succeeds
        verify_ok = await ac.post(f"{BASE}/verify-email", json={"email": unique_email, "code": valid_code})
        assert verify_ok.status_code == 200
        assert verify_ok.json()["is_email_verified"] is True

        # 6. Login now succeeds
        login_ok = await ac.post(f"{BASE}/login", json={"email": unique_email, "password": password})
        assert login_ok.status_code == 200
        tokens = login_ok.json()
        assert "access_token" in tokens
        assert "refresh_token" in tokens


@pytest.mark.asyncio
async def test_resend_otp_flow(monkeypatch):
    """When EMAIL_VERIFICATION_REQUIRED=True, resend OTP creates new code and permits verification."""
    monkeypatch.setattr(settings, "EMAIL_VERIFICATION_REQUIRED", True)
    unique_email = f"resend_user_{uuid.uuid4().hex[:8]}@example.com"
    password = "StrongPass1"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Register
        reg = await ac.post(f"{BASE}/register", json={
            "full_name": "Resend Tester",
            "email": unique_email,
            "password": password,
            "role": "student",
        })
        assert reg.status_code == 201

        # Request resend OTP
        resend_resp = await ac.post(f"{BASE}/resend-otp", json={"email": unique_email})
        assert resend_resp.status_code == 202

        # Fetch latest OTP from database
        async with AsyncSessionLocal() as session:
            user_res = await session.execute(select(User).where(User.email == unique_email))
            user = user_res.scalar_one()
            otp_res = await session.execute(
                select(OTPCode)
                .where(OTPCode.user_id == user.id, OTPCode.purpose == OTPPurpose.EMAIL_VERIFICATION)
                .order_by(OTPCode.created_at.desc())
            )
            otp = otp_res.scalars().first()
            assert otp is not None
            valid_code = otp.code

        # Verify with resent OTP
        verify_ok = await ac.post(f"{BASE}/verify-email", json={"email": unique_email, "code": valid_code})
        assert verify_ok.status_code == 200
        assert verify_ok.json()["is_email_verified"] is True

        # Successful login
        login_ok = await ac.post(f"{BASE}/login", json={"email": unique_email, "password": password})
        assert login_ok.status_code == 200
