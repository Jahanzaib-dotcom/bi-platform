"""
Unit tests for app/engines/contact/validator.py

DNS MX tests are mocked so the suite passes offline / in CI.
Phone tests use the real phonenumbers library (no network required).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.engines.contact.validator import (
    Confidence,
    EmailStatus,
    EmailValidator,
    PhoneStatus,
    PhoneValidator,
    validate_email,
    validate_phone,
)


# ─── Phone tests (no network, phonenumbers lib only) ──────────────────────────

class TestPhoneValidator:
    def setup_method(self):
        self.v = PhoneValidator(default_region="PK")

    def test_pk_mobile_valid_and_whatsapp_eligible(self):
        result = self.v.validate("+923001234567")
        assert result.status == PhoneStatus.VALID
        assert result.e164 == "+923001234567"
        assert result.whatsapp_eligible is True
        assert result.country_code == "PK"

    def test_pk_mobile_without_plus_parsed_as_pk(self):
        # Without + prefix, should still parse with default_region=PK
        result = self.v.validate("03001234567")
        assert result.status == PhoneStatus.VALID
        assert result.whatsapp_eligible is True

    def test_pk_landline_not_whatsapp_eligible(self):
        # Valid Islamabad landline: +92 51 9999999 (7 digits after area code 51)
        result = self.v.validate("+92519999999")
        assert result.status == PhoneStatus.VALID
        assert result.whatsapp_eligible is False
        assert "FIXED" in result.number_type

    def test_us_number_fixed_line_or_mobile(self):
        # US numbers are FIXED_LINE_OR_MOBILE — must NOT be wrongly rejected
        result = self.v.validate("+12125556789")
        assert result.status == PhoneStatus.VALID
        # FIXED_LINE_OR_MOBILE → eligible (ambiguous, must not skip)
        assert result.whatsapp_eligible is True

    def test_invalid_short_number(self):
        result = self.v.validate("+123")
        assert result.status == PhoneStatus.INVALID
        assert result.whatsapp_eligible is False

    def test_garbage_string(self):
        result = self.v.validate("not-a-phone")
        assert result.status == PhoneStatus.INVALID

    def test_e164_formatting(self):
        result = self.v.validate("+92 300 123 4567")
        assert result.status == PhoneStatus.VALID
        assert result.e164 == "+923001234567"

    def test_uk_mobile_eligible(self):
        result = PhoneValidator(default_region="GB").validate("+447911123456")
        assert result.status == PhoneStatus.VALID
        assert result.whatsapp_eligible is True


# ─── Email tests (DNS mocked) ─────────────────────────────────────────────────

def _mock_mx(answers):
    """Return a dns.resolver.resolve mock that yields fake MX answers."""
    def _resolve(domain, rtype, lifetime=5.0):
        if not answers:
            raise Exception("NXDOMAIN")
        mocks = []
        for host in answers:
            m = MagicMock()
            m.exchange = host + "."
            mocks.append(m)
        return mocks
    return _resolve


class TestEmailValidator:
    def setup_method(self):
        self.v = EmailValidator(smtp_rcpt=False)

    def test_valid_email_with_mx(self):
        with patch("dns.resolver.resolve", side_effect=_mock_mx(["gmail-smtp-in.l.google.com"])):
            result = self.v.validate("owner@mybusiness.com")
        assert result.status == EmailStatus.VALID
        assert result.is_usable is True
        assert result.priority == "normal"

    def test_info_email_low_priority_but_valid(self):
        with patch("dns.resolver.resolve", side_effect=_mock_mx(["mx1.example.com"])):
            result = self.v.validate("info@mybusiness.com")
        assert result.status == EmailStatus.VALID
        assert result.priority == "low"
        assert result.is_usable is True  # kept, not rejected

    def test_admin_email_kept_low_priority(self):
        with patch("dns.resolver.resolve", side_effect=_mock_mx(["mx1.example.com"])):
            result = self.v.validate("admin@mybusiness.com")
        assert result.is_usable is True
        assert result.priority == "low"

    def test_noreply_rejected(self):
        result = self.v.validate("noreply@company.com")
        assert result.status == EmailStatus.INVALID

    def test_example_domain_rejected(self):
        result = self.v.validate("test@example.com")
        assert result.status == EmailStatus.INVALID

    def test_no_mx_record(self):
        with patch("dns.resolver.resolve", side_effect=_mock_mx([])):
            result = self.v.validate("user@thisdoesnotexist99.com")
        assert result.status == EmailStatus.INVALID

    def test_dns_timeout_returns_unverifiable(self):
        import dns.exception

        def _timeout(domain, rtype, lifetime=5.0):
            raise dns.exception.Timeout()

        with patch("dns.resolver.resolve", side_effect=_timeout):
            result = self.v.validate("owner@somesite.pk")
        assert result.status == EmailStatus.UNVERIFIABLE
        assert result.is_usable is True  # benefit of the doubt

    def test_asset_false_positive_rejected(self):
        result = self.v.validate("image@icon.png")
        assert result.status == EmailStatus.INVALID

    def test_module_level_validate_email(self):
        with patch("dns.resolver.resolve", side_effect=_mock_mx(["mx.gmail.com"])):
            result = validate_email("hello@company.com")
        assert result.is_usable is True

    def test_module_level_validate_phone(self):
        result = validate_phone("+923001234567")
        assert result.whatsapp_eligible is True
