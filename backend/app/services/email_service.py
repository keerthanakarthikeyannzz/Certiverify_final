"""
Async email dispatch via SMTP (e.g. Gmail, SendGrid SMTP relay).
In DEBUG mode, emails are printed to console instead of actually sent,
so the project runs out-of-the-box without SMTP credentials configured.
"""
import logging
from email.message import EmailMessage

import aiosmtplib

from app.core.config import settings

logger = logging.getLogger("certiverify.email")


async def send_email(to: str, subject: str, html_body: str) -> None:
    is_dev = settings.ENV.lower() in ("development", "dev") or settings.DEBUG
    if not settings.SMTP_USER:
        if is_dev:
            logger.info("[DEV EMAIL] To: %s | Subject: %s\n%s", to, subject, html_body)
            print(f"\n==================== [DEV EMAIL] ====================\nTo: {to}\nSubject: {subject}\n{html_body}\n====================================================\n")
            return
        logger.error("SMTP not configured in production mode. Cannot send email to %s", to)
        raise RuntimeError("Email delivery service not configured in production.")


    message = EmailMessage()
    message["From"] = settings.EMAIL_FROM
    message["To"] = to
    message["Subject"] = subject
    message.add_alternative(html_body, subtype="html")

    await aiosmtplib.send(
        message,
        hostname=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        start_tls=True,
        username=settings.SMTP_USER,
        password=settings.SMTP_PASSWORD,
    )


async def send_otp_email(to: str, otp_code: str, purpose: str) -> None:
    subject = "Your CertiVerify AI Verification Code"
    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:auto">
      <h2 style="color:#1f2937">CertiVerify AI</h2>
      <p>Your one-time verification code for <b>{purpose.replace('_', ' ')}</b> is:</p>
      <p style="font-size:28px;font-weight:bold;letter-spacing:4px;color:#2563eb">{otp_code}</p>
      <p>This code expires in {settings.OTP_EXPIRE_MINUTES} minutes. If you did not request this, ignore this email.</p>
    </div>
    """
    await send_email(to, subject, html_body)


async def send_password_reset_email(to: str, reset_link: str) -> None:
    subject = "Reset Your CertiVerify AI Password"
    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:auto">
      <h2 style="color:#1f2937">CertiVerify AI</h2>
      <p>Click below to reset your password. This link expires in 30 minutes.</p>
      <p><a href="{reset_link}" style="background:#2563eb;color:#fff;padding:10px 20px;
         border-radius:6px;text-decoration:none">Reset Password</a></p>
    </div>
    """
    await send_email(to, subject, html_body)
