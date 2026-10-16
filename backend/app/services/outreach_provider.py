"""
Pluggable outreach email provider.

Providers
---------
SmtpProvider  — wraps existing email_sender.py; for manual single sends only.
BrevoProvider — async REST POST to Brevo v3 API; free tier = 300 emails/day.
SesProvider   — stub; raises NotImplementedError with a clear message.

Factory
-------
get_outreach_provider() reads OUTREACH_EMAIL_PROVIDER from config:
  smtp  → SmtpProvider
  brevo → BrevoProvider
  ses   → SesProvider (raises NotImplementedError on use)
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# ─── Result type (shared with email_sender) ──────────────────────────────────

@dataclass
class SendResult:
    success: bool
    error: Optional[str] = None
    provider: str = "unknown"


# ─── Abstract interface ───────────────────────────────────────────────────────

class OutreachEmailProvider(ABC):
    """All outreach providers implement this interface."""

    @abstractmethod
    async def send(
        self,
        to_email: str,
        subject: str,
        body_html: str,
        body_text: str = "",
        reply_to: Optional[str] = None,
    ) -> SendResult:
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...


# ─── SMTP provider (manual single sends) ─────────────────────────────────────

class SmtpProvider(OutreachEmailProvider):
    """Delegates to the existing email_sender module (Gmail SMTP)."""

    @property
    def provider_name(self) -> str:
        return "smtp"

    async def send(
        self,
        to_email: str,
        subject: str,
        body_html: str,
        body_text: str = "",
        reply_to: Optional[str] = None,
    ) -> SendResult:
        from app.services.email_sender import send_email
        result = await send_email(
            to_email=to_email,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            reply_to=reply_to,
        )
        return SendResult(
            success=result.success,
            error=result.error,
            provider="smtp",
        )


# ─── Brevo provider (bulk cold outreach, free tier) ──────────────────────────

class BrevoProvider(OutreachEmailProvider):
    """
    Sends via Brevo (formerly Sendinblue) REST API v3.
    Free tier: 300 emails/day, no credit card required.
    Requires BREVO_API_KEY in .env.
    """

    _API_URL = "https://api.brevo.com/v3/smtp/email"

    @property
    def provider_name(self) -> str:
        return "brevo"

    async def send(
        self,
        to_email: str,
        subject: str,
        body_html: str,
        body_text: str = "",
        reply_to: Optional[str] = None,
    ) -> SendResult:
        try:
            import httpx
            from app.core.config import settings

            api_key = settings.BREVO_API_KEY
            if not api_key:
                return SendResult(success=False, error="BREVO_API_KEY not set", provider="brevo")

            from_email = settings.SMTP_FROM_EMAIL or settings.SMTP_USERNAME
            from_name = settings.SMTP_FROM_NAME or "Web Services Team"

            payload: dict = {
                "sender": {"name": from_name, "email": from_email},
                "to": [{"email": to_email}],
                "subject": subject,
                "htmlContent": body_html,
            }
            if body_text:
                payload["textContent"] = body_text
            if reply_to:
                payload["replyTo"] = {"email": reply_to}

            headers = {
                "api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            }

            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(self._API_URL, json=payload, headers=headers)

            if resp.status_code in (200, 201):
                return SendResult(success=True, provider="brevo")

            error_detail = resp.text[:300]
            logger.warning("Brevo send failed: HTTP %s — %s", resp.status_code, error_detail)
            return SendResult(
                success=False,
                error=f"Brevo API error {resp.status_code}: {error_detail}",
                provider="brevo",
            )

        except Exception as exc:
            logger.exception("BrevoProvider.send raised: %s", exc)
            return SendResult(success=False, error=str(exc), provider="brevo")


# ─── SES stub ────────────────────────────────────────────────────────────────

class SesProvider(OutreachEmailProvider):
    """
    Amazon SES provider stub.
    Not implemented — configure OUTREACH_EMAIL_PROVIDER=smtp or brevo instead.
    """

    @property
    def provider_name(self) -> str:
        return "ses"

    async def send(self, *args, **kwargs) -> SendResult:
        raise NotImplementedError(
            "SES provider is not implemented. "
            "Set OUTREACH_EMAIL_PROVIDER=smtp or OUTREACH_EMAIL_PROVIDER=brevo in .env."
        )


# ─── Factory ─────────────────────────────────────────────────────────────────

def get_outreach_provider() -> OutreachEmailProvider:
    """Return the configured outreach provider based on OUTREACH_EMAIL_PROVIDER."""
    from app.core.config import settings
    provider = (settings.OUTREACH_EMAIL_PROVIDER or "smtp").lower().strip()

    if provider == "brevo":
        return BrevoProvider()
    if provider == "ses":
        return SesProvider()
    # Default: smtp
    return SmtpProvider()
