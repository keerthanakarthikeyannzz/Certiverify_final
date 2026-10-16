"""
Security core: password hashing (bcrypt), JWT issuing/verification, OTP generation.

Uses bcrypt directly (no passlib) to avoid the passlib 1.7.4 / bcrypt ≥4.x
incompatibility (removed __about__ attribute + 72-byte wrap-bug detection crash).
Passwords are SHA-256 pre-hashed before bcrypt so the 72-byte limit is never hit.
"""
import hashlib
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import jwt, JWTError

from app.core.config import settings


# ---------- Password hashing ----------

def _prehash(password: str) -> bytes:
    """SHA-256 pre-hash → 64-char hex string → always < 72 bytes for bcrypt."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest().encode("utf-8")


def hash_password(password: str) -> str:
    hashed = bcrypt.hashpw(_prehash(password), bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(_prehash(plain_password), hashed_password.encode("utf-8"))


# ---------- JWT ----------

def create_access_token(subject: str, extra_claims: dict[str, Any] | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {"sub": subject, "exp": expire, "type": "access"}
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {"sub": subject, "exp": expire, "type": "refresh"}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None


# ---------- OTP ----------

def generate_otp(length: int = 6) -> str:
    return "".join(secrets.choice(string.digits) for _ in range(length))



def otp_expiry() -> datetime:
    """Returns naive UTC datetime to match TIMESTAMP WITHOUT TIME ZONE DB columns."""
    return datetime.utcnow() + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)
