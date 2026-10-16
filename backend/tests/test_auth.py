"""
Unit tests for Module 1 - Authentication.
Run with: pytest -v
Uses an isolated in-memory-style Postgres test DB (configure TEST_DATABASE_URL)
or point DATABASE_URL at a disposable test schema before running.
"""
import uuid
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app

BASE = "/api/v1/auth"


@pytest.mark.asyncio
async def test_register_new_user():
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
    assert "is_email_verified" in body


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
async def test_login_blocked_before_email_verification():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        unique_email = f"unverified_{uuid.uuid4().hex[:8]}@example.com"
        await ac.post(f"{BASE}/register", json={
            "full_name": "Unverified", "email": unique_email,
            "password": "StrongPass1", "role": "student",
        })
        resp = await ac.post(f"{BASE}/login", json={
            "email": unique_email, "password": "StrongPass1",
        })
    assert resp.status_code == 403
    assert "not verified" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_login_wrong_password():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(f"{BASE}/login", json={
            "email": "nonexistent@example.com", "password": "whatever123",
        })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_register_verify_login_complete_flow():
    """Full lifecycle: register -> blocked login -> verify-email with OTP -> successful login."""
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
        from app.db.database import AsyncSessionLocal
        from app.models.models import User, OTPCode, OTPPurpose
        from sqlalchemy import select
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
async def test_resend_otp_flow():
    """Resend OTP creates new code and permits subsequent verification."""
    unique_email = f"resend_user_{uuid.uuid4().hex[:8]}@example.com"
    password = "StrongPass1"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Register
        await ac.post(f"{BASE}/register", json={
            "full_name": "Resend Tester",
            "email": unique_email,
            "password": password,
            "role": "student",
        })

        # Request resend OTP
        resend_resp = await ac.post(f"{BASE}/resend-otp", json={"email": unique_email})
        assert resend_resp.status_code == 202

        # Fetch latest OTP from database
        from app.db.database import AsyncSessionLocal
        from app.models.models import User, OTPCode, OTPPurpose
        from sqlalchemy import select
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
