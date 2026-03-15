"""
Tests for the validation layer.

Run with: python -m pytest tests/test_validators.py -v
"""

import pytest

from obscura.validators import (
    ValidationResult,
    Validator,
    LuhnValidator,
    CardPrefixValidator,
    SSNValidator,
    AadhaarValidator,
    NotLabelValidator,
    NotPlaceholderValidator,
    MinLengthValidator,
    BoundaryValidator,
    RFCEmailValidator,
    MinDigitsValidator,
    ValidatorRegistry,
)


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        result = ValidationResult(is_valid=True)
        assert result.is_valid is True
        assert result.confidence_adjustment == 0.0
        assert result.rejection_reason is None

    def test_with_all_fields(self):
        """Should accept all fields."""
        result = ValidationResult(
            is_valid=False,
            confidence_adjustment=-0.5,
            rejection_reason="invalid_checksum"
        )
        assert result.is_valid is False
        assert result.confidence_adjustment == -0.5
        assert result.rejection_reason == "invalid_checksum"


class TestLuhnValidator:
    """Tests for credit card Luhn checksum validation."""

    @pytest.fixture
    def validator(self):
        return LuhnValidator()

    def test_valid_visa(self, validator):
        """Should pass for valid Visa card with correct Luhn checksum."""
        result = validator.validate("4532015112830366", "financial_account")
        assert result.is_valid is True
        assert result.confidence_adjustment == 0.2

    def test_valid_mastercard(self, validator):
        """Should pass for valid MasterCard."""
        result = validator.validate("5425233430109903", "financial_account")
        assert result.is_valid is True
        assert result.confidence_adjustment == 0.2

    def test_invalid_checksum(self, validator):
        """Should fail for invalid Luhn checksum."""
        result = validator.validate("4532015112830367", "financial_account")
        assert result.is_valid is False
        assert result.rejection_reason == "invalid_luhn_checksum"

    def test_formatted_card(self, validator):
        """Should work with formatted card numbers (dashes/spaces)."""
        result = validator.validate("4532-0151-1283-0366", "financial_account")
        assert result.is_valid is True
        assert result.confidence_adjustment == 0.2

    def test_with_spaces(self, validator):
        """Should work with spaces."""
        result = validator.validate("4532 0151 1283 0366", "financial_account")
        assert result.is_valid is True

    def test_non_financial_type_skipped(self, validator):
        """Should skip validation for non-financial types."""
        result = validator.validate("1234567890", "phone")
        assert result.is_valid is True
        assert result.confidence_adjustment == 0.0  # No boost

    def test_valid_amex(self, validator):
        """Should pass for valid American Express card."""
        result = validator.validate("378282246310005", "financial_account")
        assert result.is_valid is True

    def test_too_short(self, validator):
        """Should handle short inputs gracefully."""
        result = validator.validate("411", "financial_account")
        assert result.is_valid is False


class TestCardPrefixValidator:
    """Tests for credit card prefix validation."""

    @pytest.fixture
    def validator(self):
        return CardPrefixValidator()

    def test_visa_prefix(self, validator):
        """Visa cards start with 4."""
        result = validator.validate("4111111111111111", "financial_account")
        assert result.is_valid is True
        assert result.confidence_adjustment == 0.1

    def test_mastercard_prefix_51(self, validator):
        """MasterCard starts with 51-55."""
        result = validator.validate("5111111111111111", "financial_account")
        assert result.is_valid is True

    def test_mastercard_prefix_55(self, validator):
        """MasterCard starts with 51-55."""
        result = validator.validate("5555555555554444", "financial_account")
        assert result.is_valid is True

    def test_amex_prefix_34(self, validator):
        """Amex starts with 34 or 37."""
        result = validator.validate("341111111111111", "financial_account")
        assert result.is_valid is True

    def test_amex_prefix_37(self, validator):
        """Amex starts with 34 or 37."""
        result = validator.validate("371111111111111", "financial_account")
        assert result.is_valid is True

    def test_discover_prefix_6011(self, validator):
        """Discover starts with 6011 or 65."""
        result = validator.validate("6011111111111111", "financial_account")
        assert result.is_valid is True

    def test_discover_prefix_65(self, validator):
        """Discover starts with 6011 or 65."""
        result = validator.validate("6511111111111111", "financial_account")
        assert result.is_valid is True

    def test_invalid_prefix(self, validator):
        """Should reject unknown card prefixes."""
        result = validator.validate("1234567890123456", "financial_account")
        assert result.is_valid is False
        assert result.rejection_reason == "unknown_card_prefix"

    def test_non_financial_type_skipped(self, validator):
        """Should skip validation for non-financial types."""
        result = validator.validate("1234567890", "email")
        assert result.is_valid is True
        assert result.confidence_adjustment == 0.0


class TestSSNValidator:
    """Tests for SSN validation."""

    @pytest.fixture
    def validator(self):
        return SSNValidator()

    def test_valid_ssn(self, validator):
        """Should pass for valid SSN format."""
        result = validator.validate("123-45-6789", "government_id")
        assert result.is_valid is True
        assert result.confidence_adjustment == 0.15

    def test_valid_ssn_no_dashes(self, validator):
        """Should pass for valid SSN without dashes."""
        result = validator.validate("123456789", "government_id")
        assert result.is_valid is True

    def test_invalid_area_000(self, validator):
        """Area number 000 is invalid."""
        result = validator.validate("000-45-6789", "government_id")
        assert result.is_valid is False
        assert result.rejection_reason == "invalid_ssn_area"

    def test_invalid_area_666(self, validator):
        """Area number 666 is never used."""
        result = validator.validate("666-45-6789", "government_id")
        assert result.is_valid is False
        assert result.rejection_reason == "invalid_ssn_area"

    def test_invalid_area_900s(self, validator):
        """Area numbers 900-999 are invalid."""
        result = validator.validate("900-45-6789", "government_id")
        assert result.is_valid is False
        assert result.rejection_reason == "invalid_ssn_area"

    def test_invalid_area_950(self, validator):
        """Area number 950 is invalid (900+)."""
        result = validator.validate("950-45-6789", "government_id")
        assert result.is_valid is False

    def test_woolworth_ssn(self, validator):
        """The famous Woolworth SSN should be rejected."""
        result = validator.validate("078-05-1120", "government_id")
        assert result.is_valid is False
        assert result.rejection_reason == "known_invalid_ssn"

    def test_invalid_group_00(self, validator):
        """Group number 00 is invalid."""
        result = validator.validate("123-00-6789", "government_id")
        assert result.is_valid is False
        assert result.rejection_reason == "invalid_ssn_group"

    def test_invalid_serial_0000(self, validator):
        """Serial number 0000 is invalid."""
        result = validator.validate("123-45-0000", "government_id")
        assert result.is_valid is False
        assert result.rejection_reason == "invalid_ssn_serial"

    def test_non_government_id_skipped(self, validator):
        """Should skip validation for non-government_id types."""
        result = validator.validate("000-00-0000", "phone")
        assert result.is_valid is True
        assert result.confidence_adjustment == 0.0


class TestAadhaarValidator:
    """Tests for Indian Aadhaar number validation."""

    @pytest.fixture
    def validator(self):
        return AadhaarValidator()

    def test_valid_aadhaar(self, validator):
        """Should pass for valid Aadhaar with correct Verhoeff checksum."""
        # Valid Aadhaar: 234123412346 (passes Verhoeff)
        result = validator.validate("234123412346", "government_id")
        assert result.is_valid is True
        assert result.confidence_adjustment == 0.2

    def test_invalid_first_digit_0(self, validator):
        """First digit cannot be 0."""
        result = validator.validate("034123412346", "government_id")
        assert result.is_valid is False
        assert result.rejection_reason == "invalid_aadhaar_start"

    def test_invalid_first_digit_1(self, validator):
        """First digit cannot be 1."""
        result = validator.validate("134123412346", "government_id")
        assert result.is_valid is False
        assert result.rejection_reason == "invalid_aadhaar_start"

    def test_invalid_verhoeff_checksum(self, validator):
        """Should reject invalid Verhoeff checksum."""
        result = validator.validate("234123412345", "government_id")
        assert result.is_valid is False
        assert result.rejection_reason == "invalid_verhoeff_checksum"

    def test_wrong_length(self, validator):
        """Aadhaar with wrong length is skipped (not an Aadhaar)."""
        result = validator.validate("2341234123", "government_id")
        # 10 digits is not an Aadhaar format, so validator skips it
        assert result.is_valid is True
        assert result.confidence_adjustment == 0.0  # No boost since not validated

    def test_with_spaces(self, validator):
        """Should work with formatted Aadhaar (spaces)."""
        result = validator.validate("2341 2341 2346", "government_id")
        assert result.is_valid is True

    def test_non_government_id_skipped(self, validator):
        """Should skip validation for non-government_id types."""
        result = validator.validate("034123412346", "email")
        assert result.is_valid is True


class TestNotLabelValidator:
    """Tests for rejecting label words like 'Email:', 'Phone', etc."""

    @pytest.fixture
    def validator(self):
        return NotLabelValidator()

    def test_rejects_email_label(self, validator):
        """Should reject 'Email' as a label word."""
        result = validator.validate("Email", "email")
        assert result.is_valid is False
        assert result.rejection_reason == "is_label_word"

    def test_rejects_email_colon(self, validator):
        """Should reject 'Email:' with trailing colon."""
        result = validator.validate("Email:", "email")
        assert result.is_valid is False
        assert result.rejection_reason == "is_label_word"

    def test_rejects_case_insensitive(self, validator):
        """Should reject regardless of case."""
        result = validator.validate("EMAIL", "email")
        assert result.is_valid is False

    def test_accepts_actual_email(self, validator):
        """Should accept actual email addresses."""
        result = validator.validate("john@example.com", "email")
        assert result.is_valid is True

    def test_rejects_phone_label(self, validator):
        """Should reject 'Phone' as a label."""
        result = validator.validate("Phone", "phone")
        assert result.is_valid is False

    def test_rejects_ssn_label(self, validator):
        """Should reject 'SSN' as a label."""
        result = validator.validate("ssn", "government_id")
        assert result.is_valid is False

    def test_rejects_name_label(self, validator):
        """Should reject 'Name' as a label."""
        result = validator.validate("Name:", "person_name")
        assert result.is_valid is False

    def test_rejects_address_label(self, validator):
        """Should reject 'Address' as a label."""
        result = validator.validate("address", "address")
        assert result.is_valid is False

    def test_accepts_actual_value(self, validator):
        """Should accept actual values that aren't labels."""
        result = validator.validate("555-123-4567", "phone")
        assert result.is_valid is True


class TestNotPlaceholderValidator:
    """Tests for rejecting placeholder patterns."""

    @pytest.fixture
    def validator(self):
        return NotPlaceholderValidator()

    def test_rejects_email_placeholder(self, validator):
        """Should reject [EMAIL_1] style placeholders."""
        result = validator.validate("[EMAIL_1]", "email")
        assert result.is_valid is False
        assert result.rejection_reason == "is_placeholder"

    def test_rejects_phone_placeholder(self, validator):
        """Should reject [PHONE_2] style placeholders."""
        result = validator.validate("[PHONE_2]", "phone")
        assert result.is_valid is False

    def test_rejects_ssn_placeholder(self, validator):
        """Should reject [SSN_1] style placeholders."""
        result = validator.validate("[SSN_1]", "government_id")
        assert result.is_valid is False

    def test_rejects_curly_placeholder(self, validator):
        """Should reject {EMAIL} style placeholders."""
        result = validator.validate("{EMAIL}", "email")
        assert result.is_valid is False

    def test_rejects_angle_placeholder(self, validator):
        """Should reject <PHONE> style placeholders."""
        result = validator.validate("<PHONE>", "phone")
        assert result.is_valid is False

    def test_accepts_actual_email(self, validator):
        """Should accept actual email addresses."""
        result = validator.validate("john@example.com", "email")
        assert result.is_valid is True

    def test_accepts_value_with_brackets(self, validator):
        """Should accept values that happen to have brackets but aren't placeholders."""
        result = validator.validate("[Actual Name]", "person_name")
        # This should pass because it doesn't match placeholder patterns
        assert result.is_valid is True


class TestMinLengthValidator:
    """Tests for minimum length validation."""

    @pytest.fixture
    def validator(self):
        return MinLengthValidator()

    def test_email_too_short(self, validator):
        """Email must be at least 5 characters."""
        result = validator.validate("a@b", "email")
        assert result.is_valid is False
        assert result.rejection_reason == "too_short"

    def test_email_valid_length(self, validator):
        """Email at minimum length should pass."""
        result = validator.validate("a@b.c", "email")
        assert result.is_valid is True

    def test_phone_too_short(self, validator):
        """Phone must be at least 7 characters."""
        result = validator.validate("123456", "phone")
        assert result.is_valid is False

    def test_phone_valid_length(self, validator):
        """Phone at minimum length should pass."""
        result = validator.validate("1234567", "phone")
        assert result.is_valid is True

    def test_address_too_short(self, validator):
        """Address must be at least 10 characters."""
        result = validator.validate("123 Main", "address")
        assert result.is_valid is False

    def test_address_valid_length(self, validator):
        """Address at minimum length should pass."""
        result = validator.validate("123 Main St", "address")
        assert result.is_valid is True

    def test_unknown_type_passes(self, validator):
        """Unknown types should pass with default min length."""
        result = validator.validate("ab", "unknown_type")
        assert result.is_valid is True


class TestBoundaryValidator:
    """Tests for word boundary validation in context."""

    @pytest.fixture
    def validator(self):
        return BoundaryValidator()

    def test_valid_boundaries_spaces(self, validator):
        """Should pass when entity has word boundaries."""
        result = validator.validate(
            "john@example.com",
            "email",
            context="Contact john@example.com for help"
        )
        assert result.is_valid is True

    def test_valid_boundaries_start(self, validator):
        """Should pass when entity is at start of context."""
        result = validator.validate(
            "john@example.com",
            "email",
            context="john@example.com is the email"
        )
        assert result.is_valid is True

    def test_valid_boundaries_end(self, validator):
        """Should pass when entity is at end of context."""
        result = validator.validate(
            "john@example.com",
            "email",
            context="Email: john@example.com"
        )
        assert result.is_valid is True

    def test_no_context_passes(self, validator):
        """Should pass when no context is provided."""
        result = validator.validate("john@example.com", "email", context=None)
        assert result.is_valid is True

    def test_entity_not_in_context(self, validator):
        """Should pass when entity not found in context (edge case)."""
        result = validator.validate(
            "john@example.com",
            "email",
            context="Contact support for help"
        )
        assert result.is_valid is True

    def test_invalid_boundary_prefix(self, validator):
        """Should reject when entity has no left boundary."""
        result = validator.validate(
            "example.com",
            "email",
            context="testexample.com is not valid"
        )
        assert result.is_valid is False
        assert result.rejection_reason == "no_word_boundary"


class TestRFCEmailValidator:
    """Tests for RFC 5322 email validation."""

    @pytest.fixture
    def validator(self):
        return RFCEmailValidator()

    def test_valid_email(self, validator):
        """Should pass for valid email address."""
        result = validator.validate("john@example.com", "email")
        assert result.is_valid is True

    def test_valid_email_with_subdomain(self, validator):
        """Should pass for email with subdomain."""
        result = validator.validate("john@mail.example.com", "email")
        assert result.is_valid is True

    def test_valid_email_with_plus(self, validator):
        """Should pass for email with plus addressing."""
        result = validator.validate("john+test@example.com", "email")
        assert result.is_valid is True

    def test_invalid_no_at(self, validator):
        """Should reject email without @."""
        result = validator.validate("johnexample.com", "email")
        assert result.is_valid is False
        assert result.rejection_reason == "invalid_email_format"

    def test_invalid_no_domain(self, validator):
        """Should reject email without domain."""
        result = validator.validate("john@", "email")
        assert result.is_valid is False

    def test_invalid_no_local(self, validator):
        """Should reject email without local part."""
        result = validator.validate("@example.com", "email")
        assert result.is_valid is False

    def test_non_email_type_skipped(self, validator):
        """Should skip validation for non-email types."""
        result = validator.validate("not-an-email", "phone")
        assert result.is_valid is True


class TestMinDigitsValidator:
    """Tests for minimum digits validation (for phone numbers)."""

    @pytest.fixture
    def validator(self):
        return MinDigitsValidator(min_digits=7)

    def test_valid_phone(self, validator):
        """Should pass for phone with enough digits."""
        result = validator.validate("555-123-4567", "phone")
        assert result.is_valid is True

    def test_too_few_digits(self, validator):
        """Should reject when not enough digits."""
        result = validator.validate("123456", "phone")
        assert result.is_valid is False
        assert result.rejection_reason == "too_few_digits"

    def test_counts_only_digits(self, validator):
        """Should only count digits, not formatting."""
        result = validator.validate("(555) 123", "phone")  # Only 6 digits
        assert result.is_valid is False

    def test_non_phone_type_skipped(self, validator):
        """Should skip validation for non-phone types."""
        result = validator.validate("123", "email")
        assert result.is_valid is True

    def test_custom_min_digits(self):
        """Should respect custom min_digits parameter."""
        validator = MinDigitsValidator(min_digits=10)
        result = validator.validate("123456789", "phone")  # 9 digits
        assert result.is_valid is False


class TestValidatorRegistry:
    """Tests for the validator registry."""

    @pytest.fixture
    def registry(self):
        return ValidatorRegistry()

    def test_registry_validates_credit_card(self, registry):
        """Should validate credit card with all applicable validators."""
        result = registry.validate("4532015112830366", "financial_account")
        assert result.is_valid is True
        # Should have confidence boost from Luhn + CardPrefix
        assert result.confidence_adjustment > 0

    def test_registry_rejects_label_word(self, registry):
        """Universal validator should reject label words."""
        result = registry.validate("Email", "email")
        assert result.is_valid is False
        assert result.rejection_reason == "is_label_word"

    def test_registry_rejects_invalid_ssn(self, registry):
        """Should reject invalid SSN."""
        result = registry.validate("000-12-3456", "government_id")
        assert result.is_valid is False
        assert result.rejection_reason == "invalid_ssn_area"

    def test_registry_rejects_placeholder(self, registry):
        """Should reject placeholder patterns."""
        result = registry.validate("[EMAIL_1]", "email")
        assert result.is_valid is False
        assert result.rejection_reason == "is_placeholder"

    def test_registry_aggregates_confidence(self, registry):
        """Should aggregate confidence adjustments from passing validators."""
        result = registry.validate("4532015112830366", "financial_account")
        # Luhn (+0.2) + CardPrefix (+0.1) = +0.3
        assert result.confidence_adjustment == pytest.approx(0.3, abs=0.01)

    def test_registry_validates_email(self, registry):
        """Should validate email with RFC validator."""
        result = registry.validate("john@example.com", "email")
        assert result.is_valid is True

    def test_registry_rejects_invalid_email(self, registry):
        """Should reject invalid email format."""
        result = registry.validate("not-an-email", "email")
        assert result.is_valid is False

    def test_registry_validates_phone(self, registry):
        """Should validate phone with digit count."""
        result = registry.validate("555-123-4567", "phone")
        assert result.is_valid is True

    def test_registry_rejects_short_phone(self, registry):
        """Should reject phone with too few digits."""
        result = registry.validate("123", "phone")
        assert result.is_valid is False

    def test_registry_with_context(self, registry):
        """Should pass context to validators."""
        result = registry.validate(
            "john@example.com",
            "email",
            context="Contact john@example.com today"
        )
        assert result.is_valid is True

    def test_registry_returns_first_rejection(self, registry):
        """Should return immediately on first rejection."""
        # This is both too short AND a label
        result = registry.validate("Em", "email")
        assert result.is_valid is False
        # Should get one of the rejection reasons


class TestIntegration:
    """Integration tests for validator combinations."""

    @pytest.fixture
    def registry(self):
        return ValidatorRegistry()

    def test_full_credit_card_validation(self, registry):
        """Valid card passes all validators."""
        # Valid Visa with correct Luhn
        result = registry.validate("4532015112830366", "financial_account")
        assert result.is_valid is True
        assert result.confidence_adjustment >= 0.3  # Luhn + Prefix

    def test_full_ssn_validation(self, registry):
        """Valid SSN passes all validators."""
        result = registry.validate("123-45-6789", "government_id")
        assert result.is_valid is True
        assert result.confidence_adjustment >= 0.15

    def test_full_email_validation(self, registry):
        """Valid email passes all validators."""
        result = registry.validate("john.doe@example.com", "email")
        assert result.is_valid is True

    def test_rejects_obvious_false_positive(self, registry):
        """Should reject obvious false positives like labels."""
        for text in ["Email:", "Phone:", "Name", "SSN", "Address:"]:
            result = registry.validate(text.lower(), "email")
            assert result.is_valid is False, f"Should reject '{text}'"
