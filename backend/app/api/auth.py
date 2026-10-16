"""
MODULE 1 - USER AUTHENTICATION
Registration, Email Verification (OTP), Login, OTP re-verification, JWT issuance,
Forgot/Reset Password, Refresh Token, Logout, Role-based access.

DEV MODE (is_email_verified auto-set to True on registration).
OTP / email-verification flow is commented out below — search for
  # [OTP-RESTORE] to re-enable it for production.
"""
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    hash_password, verify_password, create_access_token, create_refresh_token,
    decode_token, generate_otp, otp_expiry,
)
from app.db.database import get_db
from app.models.models import User, UserRole, PasswordResetToken, OTPCode, OTPPurpose
from app.schemas.auth_schemas import (
    UserRegisterRequest, UserResponse, LoginRequest, TokenResponse,
    RefreshTokenRequest, OTPVerifyRequest, ResendOTPRequest,
    ForgotPasswordRequest, ResetPasswordRequest,
)
from app.services.email_service import send_otp_email, send_password_reset_email
from app.api.deps import get_current_user

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


# ---------------------------------------------------------------------------
# REGISTER
# ---------------------------------------------------------------------------

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: UserRegisterRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    try:
        role = UserRole(payload.role)
    except ValueError:
        role_lower = (payload.role or "").lower()
        if role_lower in ("verifier", "university", "org_admin", "institution"):
            role = UserRole.UNIVERSITY
        elif role_lower in ("admin", "superadmin"):
            role = UserRole.ADMIN
        elif role_lower in ("employer", "recruiter"):
            role = UserRole.EMPLOYER
        else:
            role = UserRole.STUDENT

    user = User(
        full_name=payload.full_name,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=role,
        is_active=True,
        is_email_verified=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return user


# ---------------------------------------------------------------------------
# EMAIL VERIFICATION (OTP)
# ---------------------------------------------------------------------------

@router.post("/verify-email", status_code=status.HTTP_410_GONE)
async def verify_email():
    """Email verification via OTP has been removed; users are verified on registration."""
    raise HTTPException(status_code=410, detail="Email verification is no longer required.")


@router.post("/resend-otp", status_code=status.HTTP_410_GONE)
async def resend_otp():
    """OTP resend has been removed; users are verified on registration."""
    raise HTTPException(status_code=410, detail="Email verification is no longer required.")


# ---------------------------------------------------------------------------
# LOGIN
# ---------------------------------------------------------------------------

@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="This account has been deactivated.")

    access_token = create_access_token(subject=user.id, extra_claims={"role": user.role.value})
    refresh_token = create_refresh_token(subject=user.id)

    from app.services.audit_service import log_audit_event
    await log_audit_event(
        db,
        action="auth:login",
        entity_type="user",
        actor_user_id=user.id,
        organization_id=user.organization_id,
        entity_id=user.id,
    )

    return TokenResponse(access_token=access_token, refresh_token=refresh_token, user=user)



@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(payload: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    decoded = decode_token(payload.refresh_token)
    if not decoded or decoded.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token.")

    result = await db.execute(select(User).where(User.id == decoded["sub"]))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive.")

    access_token = create_access_token(subject=user.id, extra_claims={"role": user.role.value})
    new_refresh_token = create_refresh_token(subject=user.id)
    return TokenResponse(access_token=access_token, refresh_token=new_refresh_token, user=user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(user: User = Depends(get_current_user)):
    # Stateless JWT: logout is enforced client-side by discarding tokens.
    # For server-side revocation, maintain a token-blacklist/Redis set keyed by jti.
    return None


# ---------------------------------------------------------------------------
# FORGOT / RESET PASSWORD
# ---------------------------------------------------------------------------

@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(
    payload: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
    # [OTP-RESTORE] Restore BackgroundTasks + email sending when re-enabling email flow:
    # background_tasks: BackgroundTasks,
):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if not user:
        return {"message": "If an account exists, a reset link has been sent."}

    from app.core.security import otp_expiry  # local import avoids unused import warning
    token = secrets.token_urlsafe(32)
    db.add(PasswordResetToken(
        user_id=user.id, token=token, expires_at=otp_expiry(),
    ))
    await db.commit()

    # [OTP-RESTORE] Uncomment to actually send the reset email:
    # reset_link = f"https://app.certiverify.ai/reset-password?token={token}"
    # background_tasks.add_task(send_password_reset_email, user.email, reset_link)

    return {"message": "If an account exists, a reset link has been sent."}


@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token == payload.token)
    )
    reset_row = result.scalar_one_or_none()
    if not reset_row or reset_row.is_used:
        raise HTTPException(status_code=400, detail="Invalid or already-used reset token.")
    if reset_row.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Reset token expired. Please request a new one.")

    user_result = await db.execute(select(User).where(User.id == reset_row.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    user.hashed_password = hash_password(payload.new_password)
    reset_row.is_used = True
    await db.commit()
    return {"message": "Password has been reset successfully. Please log in."}


# ---------------------------------------------------------------------------
# CURRENT USER
# ---------------------------------------------------------------------------

@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    return user
