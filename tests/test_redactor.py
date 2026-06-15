"""
Integration tests for the PII redaction layer.
Covers: regex patterns, SpaCy NER, multi-field messages, adversarial inputs.
Run: uv run pytest tests/ -v
"""

import pytest  # noqa: F401
from vicroads_guardrails.redactor import redact_messages, _redact_text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def redact(text: str):
    """Shorthand for single-string redaction."""
    return _redact_text(text)


def has_pii(text: str, *fragments: str) -> bool:
    return any(f in text for f in fragments)


# ---------------------------------------------------------------------------
# Victorian Driver Licence (9 digits)
# ---------------------------------------------------------------------------


class TestVicDriverLicence:
    def test_basic_detection(self):
        r = redact("My licence number is 123456789.")
        assert "123456789" not in r.text
        assert "[REDACTED_VIC_DL]" in r.text
        assert "REDACTED_VIC_DL" in r.redacted_types

    def test_multiple_licences_in_one_message(self):
        r = redact("Driver A: 111222333, Driver B: 444555666.")
        assert "111222333" not in r.text
        assert "444555666" not in r.text

    def test_eight_digits_not_flagged(self):
        r = redact("Reference ID: 12345678")
        assert "12345678" in r.text
        assert not r.pii_detected

    def test_ten_digits_not_flagged(self):
        r = redact("Invoice: 1234567890")
        assert "1234567890" in r.text

    def test_licence_embedded_in_sentence(self):
        r = redact("Please check if 987654321 is active.")
        assert "987654321" not in r.text


# ---------------------------------------------------------------------------
# Email addresses
# ---------------------------------------------------------------------------


class TestEmail:
    def test_standard_email(self):
        r = redact("Contact john.smith@vicroads.vic.gov.au for details.")
        assert "john.smith" not in r.text
        assert "[REDACTED_EMAIL]" in r.text

    def test_email_with_plus(self):
        r = redact("Send to user+tag@example.com")
        assert "user+tag@example.com" not in r.text

    def test_no_false_positive_on_url(self):
        # Plain domain without @ should not trigger email pattern
        r = redact("Visit vicroads.vic.gov.au for more info.")
        assert "vicroads.vic.gov.au" in r.text


# ---------------------------------------------------------------------------
# Australian phone numbers
# ---------------------------------------------------------------------------


class TestPhone:
    def test_mobile(self):
        r = redact("Call me on 0412 345 678.")
        assert "0412 345 678" not in r.text
        assert "[REDACTED_PHONE]" in r.text

    def test_mobile_no_spaces(self):
        r = redact("Mobile: 0412345678")
        assert "0412345678" not in r.text

    def test_mobile_with_country_code(self):
        r = redact("International: +61412345678")
        assert "+61412345678" not in r.text

    def test_landline_with_area_code(self):
        r = redact("Office: (03) 9123 4567")
        assert "9123 4567" not in r.text


# ---------------------------------------------------------------------------
# Medicare numbers
# ---------------------------------------------------------------------------


class TestMedicare:
    def test_medicare_detected(self):
        r = redact("Medicare card: 2123456701")
        assert "2123456701" not in r.text
        assert "[REDACTED_MEDICARE]" in r.text

    def test_medicare_starts_with_valid_digit(self):
        # Must start with 2–6; 1xxxxxxxxx should not match
        r = redact("Reference: 1123456789")
        assert "1123456789" in r.text


# ---------------------------------------------------------------------------
# Street addresses
# ---------------------------------------------------------------------------


class TestAddress:
    def test_standard_address(self):
        r = redact("I live at 42 Wallaby Way Street, Melbourne.")
        assert "42 Wallaby Way Street" not in r.text
        assert "[REDACTED_ADDRESS]" in r.text

    def test_abbreviated_street_type(self):
        r = redact("Office at 10 Collins St")
        assert "10 Collins St" not in r.text


# ---------------------------------------------------------------------------
# SpaCy NER — names and locations
# ---------------------------------------------------------------------------


class TestNER:
    def test_person_name_redacted(self):
        r = redact("The applicant John Smith submitted the form.")
        assert "John Smith" not in r.text
        assert "[REDACTED_NAME]" in r.text

    def test_location_redacted(self):
        r = redact("The incident occurred in Melbourne CBD.")
        assert "Melbourne" not in r.text

    def test_clean_text_unchanged(self):
        text = "What are the road rules for merging lanes?"
        r = redact(text)
        assert r.text == text
        assert not r.pii_detected


# ---------------------------------------------------------------------------
# Multi-field message dicts
# ---------------------------------------------------------------------------


class TestMessageRedaction:
    def test_user_message_redacted(self):
        messages = [{"role": "user", "content": "Licence 123456789 please check."}]
        result, types = redact_messages(messages)
        assert "123456789" not in result[0]["content"]
        assert "REDACTED_VIC_DL" in types

    def test_system_message_also_redacted(self):
        messages = [
            {"role": "system", "content": "Dev key for user@company.com"},
            {"role": "user", "content": "Hello"},
        ]
        result, types = redact_messages(messages)
        assert "user@company.com" not in result[0]["content"]
        assert "REDACTED_EMAIL" in types

    def test_non_string_content_skipped(self):
        messages = [{"role": "user", "content": None}]
        result, types = redact_messages(messages)
        assert result[0]["content"] is None
        assert types == []


# ---------------------------------------------------------------------------
# Adversarial / accidental leak scenarios
# ---------------------------------------------------------------------------


class TestAdversarial:
    def test_pii_disguised_with_dashes(self):
        # Attacker writes 123-456-789 hoping to bypass word-boundary regex
        # The regex uses \b\d{9}\b so dashes break the sequence — correct behaviour:
        # this tests that our regex does NOT match (dashes interrupt digit run)
        r = redact("Licence: 123-456-789")
        assert (
            "REDACTED_VIC_DL" not in r.text
        )  # correctly not matched by 9-digit pattern

    def test_multiple_pii_types_in_one_message(self):
        text = (
            "John Smith, licence 987654321, "
            "reachable at john@example.com or 0412 000 111."
        )
        r = redact(text)
        assert "987654321" not in r.text
        assert "john@example.com" not in r.text
        assert "0412 000 111" not in r.text
        assert len(r.redacted_types) >= 3

    def test_pii_in_assistant_role_message(self):
        messages = [
            {"role": "assistant", "content": "User 123456789 has been verified."}
        ]
        result, types = redact_messages(messages)
        assert "123456789" not in result[0]["content"]

    def test_empty_message_safe(self):
        messages = [{"role": "user", "content": ""}]
        result, _ = redact_messages(messages)
        assert result[0]["content"] == ""

    def test_no_pii_returns_unchanged(self):
        original = "What is the speed limit on a freeway?"
        messages = [{"role": "user", "content": original}]
        result, types = redact_messages(messages)
        assert result[0]["content"] == original
        assert types == []
