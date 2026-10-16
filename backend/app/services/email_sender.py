from __future__ import annotations

import logging
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class SendResult:
    success: bool
    message_id: str = ""
    error: str = ""


async def send_email(
    to_email: str,
    subject: str,
    body_html: str,
    body_text: str = "",
    reply_to: str = "",
) -> SendResult:
    if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
        return SendResult(success=False, error="SMTP not configured. Set SMTP_USERNAME and SMTP_PASSWORD in .env")

    from_email = settings.SMTP_FROM_EMAIL or settings.SMTP_USERNAME
    from_name = settings.SMTP_FROM_NAME

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = to_email
    if reply_to:
        msg["Reply-To"] = reply_to

    if body_text:
        msg.attach(MIMEText(body_text, "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USERNAME,
            password=settings.SMTP_PASSWORD,
            start_tls=settings.SMTP_USE_TLS,
        )
        logger.info("Email sent to %s: %s", to_email, subject)
        return SendResult(success=True)
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to_email, exc)
        return SendResult(success=False, error=str(exc))


async def test_smtp_connection() -> SendResult:
    """Verify SMTP credentials without sending a message."""
    if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
        return SendResult(success=False, error="SMTP credentials not configured")

    try:
        async with aiosmtplib.SMTP(
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            start_tls=settings.SMTP_USE_TLS,
        ) as smtp:
            await smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        return SendResult(success=True, message_id="connection_ok")
    except Exception as exc:
        return SendResult(success=False, error=str(exc))
