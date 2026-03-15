"""
Validation layer for PII detection.

Validators filter false positives by checking:
- Checksums (Luhn for credit cards, Verhoeff for Aadhaar)
- Format rules (SSN area codes, card prefixes)
- Common false positives (labels, placeholders)
- Length requirements
- Word boundaries in context
"""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class ValidationResult:
    """Result from a validator."""

    is_valid: bool
    confidence_adjustment: float = 0.0
    rejection_reason: Optional[str] = None


class Validator(ABC):
    """Base class for all validators."""

    @abstractmethod
    def validate(
        self, text: str, entity_type: str, context: Optional[str] = None
    ) -> ValidationResult:
        """
        Validate a detected entity.

        Args:
            text: The detected text to validate
            entity_type: The type of entity (email, phone, etc.)
            context: Optional surrounding text for context-aware validation

        Returns:
            ValidationResult with is_valid, confidence_adjustment, and rejection_reason
        """
        pass


class LuhnValidator(Validator):
    """
    Validates credit card numbers using the Luhn algorithm.

    The Luhn algorithm (mod 10) is used by all major card networks
    to detect typos and invalid card numbers.
    """

    def validate(
        self, text: str, entity_type: str, context: Optional[str] = None
    ) -> ValidationResult:
        # Only validate financial accounts
        if entity_type not in ("financial_account", "credit_card"):
            return ValidationResult(is_valid=True)

        # Remove formatting characters
        digits = re.sub(r"[\s\-]", "", text)

        # Must be all digits and reasonable length for credit card
        if not digits.isdigit() or len(digits) < 13 or len(digits) > 19:
            return ValidationResult(
                is_valid=False, rejection_reason="invalid_card_format"
            )

        # Luhn algorithm
        if self._luhn_check(digits):
            return ValidationResult(is_valid=True, confidence_adjustment=0.2)
        else:
            return ValidationResult(
                is_valid=False, rejection_reason="invalid_luhn_checksum"
            )

    def _luhn_check(self, digits: str) -> bool:
        """
        Luhn algorithm implementation.

        From right to left:
        1. Double every second digit
        2. If doubled digit > 9, subtract 9
        3. Sum all digits
        4. Valid if sum % 10 == 0
        """
        total = 0
        parity = len(digits) % 2

        for i, digit in enumerate(digits):
            d = int(digit)
            if i % 2 == parity:
                d *= 2
                if d > 9:
                    d -= 9
            total += d

        return total % 10 == 0


class CardPrefixValidator(Validator):
    """
    Validates credit card prefixes (IIN/BIN ranges).

    Major card networks:
    - Visa: 4
    - MasterCard: 51-55, 2221-2720
    - American Express: 34, 37
    - Discover: 6011, 65, 644-649
    """

    # Card prefix patterns
    PREFIXES = {
        "visa": [r"^4"],
        "mastercard": [r"^5[1-5]", r"^2[2-7]"],
        "amex": [r"^3[47]"],
        "discover": [r"^6011", r"^65", r"^64[4-9]"],
    }

    def validate(
        self, text: str, entity_type: str, context: Optional[str] = None
    ) -> ValidationResult:
        # Only validate financial accounts
        if entity_type not in ("financial_account", "credit_card"):
            return ValidationResult(is_valid=True)

        # Remove formatting
        digits = re.sub(r"[\s\-]", "", text)

        if not digits.isdigit():
            return ValidationResult(is_valid=True)  # Let Luhn handle this

        # Check against known prefixes
        for card_type, patterns in self.PREFIXES.items():
            for pattern in patterns:
                if re.match(pattern, digits):
                    return ValidationResult(is_valid=True, confidence_adjustment=0.1)

        return ValidationResult(is_valid=False, rejection_reason="unknown_card_prefix")


class SSNValidator(Validator):
    """
    Validates US Social Security Numbers.

    Invalid SSNs:
    - Area 000, 666, 900-999
    - Group 00
    - Serial 0000
    - Known test/invalid SSNs (Woolworth: 078-05-1120)
    """

    # Famous invalid SSNs
    KNOWN_INVALID = {
        "078051120",  # Woolworth wallet SSN
        "219099999",  # Promotional SSN from ads
        "457555462",  # Lifelock CEO's SSN
    }

    def validate(
        self, text: str, entity_type: str, context: Optional[str] = None
    ) -> ValidationResult:
        # Only validate government IDs
        if entity_type != "government_id":
            return ValidationResult(is_valid=True)

        # Remove formatting
        digits = re.sub(r"[\s\-]", "", text)

        # SSN must be exactly 9 digits
        if not digits.isdigit() or len(digits) != 9:
            return ValidationResult(is_valid=True)  # Not an SSN, skip

        # Parse components
        area = int(digits[:3])
        group = int(digits[3:5])
        serial = int(digits[5:])

        # Check for invalid area numbers
        if area == 0 or area == 666 or area >= 900:
            return ValidationResult(is_valid=False, rejection_reason="invalid_ssn_area")

        # Check for invalid group number
        if group == 0:
            return ValidationResult(
                is_valid=False, rejection_reason="invalid_ssn_group"
            )

        # Check for invalid serial number
        if serial == 0:
            return ValidationResult(
                is_valid=False, rejection_reason="invalid_ssn_serial"
            )

        # Check known invalid SSNs
        if digits in self.KNOWN_INVALID:
            return ValidationResult(
                is_valid=False, rejection_reason="known_invalid_ssn"
            )

        return ValidationResult(is_valid=True, confidence_adjustment=0.15)


class AadhaarValidator(Validator):
    """
    Validates Indian Aadhaar numbers.

    Rules:
    - 12 digits
    - First digit cannot be 0 or 1
    - Must pass Verhoeff checksum
    """

    # Verhoeff algorithm tables
    _d = [
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
        [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
        [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
        [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
        [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
        [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
        [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
        [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
        [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
        [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
    ]

    _p = [
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
        [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
        [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
        [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
        [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
        [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
        [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
        [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
    ]

    def validate(
        self, text: str, entity_type: str, context: Optional[str] = None
    ) -> ValidationResult:
        # Only validate government IDs
        if entity_type != "government_id":
            return ValidationResult(is_valid=True)

        # Remove formatting
        digits = re.sub(r"[\s\-]", "", text)

        # Aadhaar must be exactly 12 digits
        if not digits.isdigit() or len(digits) != 12:
            return ValidationResult(is_valid=True)  # Not an Aadhaar, skip

        # First digit cannot be 0 or 1
        if digits[0] in ("0", "1"):
            return ValidationResult(
                is_valid=False, rejection_reason="invalid_aadhaar_start"
            )

        # Verhoeff checksum
        if self._verhoeff_check(digits):
            return ValidationResult(is_valid=True, confidence_adjustment=0.2)
        else:
            return ValidationResult(
                is_valid=False, rejection_reason="invalid_verhoeff_checksum"
            )

    def _verhoeff_check(self, number: str) -> bool:
        """Verhoeff checksum validation."""
        c = 0
        for i, digit in enumerate(reversed(number)):
            c = self._d[c][self._p[i % 8][int(digit)]]
        return c == 0


class NotLabelValidator(Validator):
    """
    Rejects common label words that are often mistakenly detected as PII.

    Examples: "Email", "Phone:", "Name", "SSN", "Address"
    """

    LABELS = {
        "email",
        "e-mail",
        "phone",
        "telephone",
        "tel",
        "mobile",
        "name",
        "full name",
        "first name",
        "last name",
        "ssn",
        "social security",
        "social security number",
        "address",
        "street address",
        "mailing address",
        "dob",
        "date of birth",
        "birthday",
        "credit card",
        "card number",
        "account",
        "account number",
        "password",
        "username",
        "user name",
        "id",
        "identification",
    }

    def validate(
        self, text: str, entity_type: str, context: Optional[str] = None
    ) -> ValidationResult:
        # Normalize: lowercase, strip whitespace and trailing colon
        normalized = text.lower().strip().rstrip(":")

        if normalized in self.LABELS:
            return ValidationResult(is_valid=False, rejection_reason="is_label_word")

        return ValidationResult(is_valid=True)


class NotPlaceholderValidator(Validator):
    """
    Rejects placeholder patterns like [EMAIL_1], {PHONE}, <SSN>.

    These are our own anonymization placeholders being re-detected.
    """

    PLACEHOLDER_PATTERNS = [
        r"^\[[A-Z][A-Z0-9_]*_\d+\]$",  # [EMAIL_1], [PHONE_2], [PERSON_NAME_1]
        r"^\[[A-Z][A-Z0-9_]*\]$",  # [EMAIL], [PHONE] (without number, uppercase only)
        r"^\{[A-Z][A-Z0-9_]*\}$",  # {EMAIL}, {PHONE}
        r"^<[A-Z][A-Z0-9_]*>$",  # <EMAIL>, <PHONE>
        r"^__[A-Z][A-Z0-9_]*__$",  # __EMAIL__, __PHONE__
    ]

    def __init__(self):
        self._compiled = [re.compile(p) for p in self.PLACEHOLDER_PATTERNS]

    def validate(
        self, text: str, entity_type: str, context: Optional[str] = None
    ) -> ValidationResult:
        stripped = text.strip()

        for pattern in self._compiled:
            if pattern.match(stripped):
                return ValidationResult(
                    is_valid=False, rejection_reason="is_placeholder"
                )

        return ValidationResult(is_valid=True)


class MinLengthValidator(Validator):
    """
    Validates minimum length requirements per entity type.
    """

    MIN_LENGTHS = {
        "email": 5,  # a@b.c
        "phone": 7,  # Minimum phone digits
        "address": 10,  # "123 Main St"
        "person_name": 2,  # "Li"
        "government_id": 5,  # Varies by type
        "financial_account": 8,  # Minimum for account numbers
        "date_of_birth": 6,  # "1/1/90"
        "medical_id": 4,
        "digital_id": 3,
        "reference_number": 3,
    }

    DEFAULT_MIN = 1

    def validate(
        self, text: str, entity_type: str, context: Optional[str] = None
    ) -> ValidationResult:
        min_len = self.MIN_LENGTHS.get(entity_type, self.DEFAULT_MIN)

        if len(text) < min_len:
            return ValidationResult(is_valid=False, rejection_reason="too_short")

        return ValidationResult(is_valid=True)


class BoundaryValidator(Validator):
    """
    Validates that entities have proper word boundaries in context.

    Rejects entities that appear to be substrings of larger words.
    """

    def validate(
        self, text: str, entity_type: str, context: Optional[str] = None
    ) -> ValidationResult:
        # Skip if no context provided
        if not context:
            return ValidationResult(is_valid=True)

        # Find the entity in context
        idx = context.find(text)
        if idx == -1:
            # Entity not in context (edge case)
            return ValidationResult(is_valid=True)

        # Check left boundary
        if idx > 0:
            left_char = context[idx - 1]
            if left_char.isalnum():
                return ValidationResult(
                    is_valid=False, rejection_reason="no_word_boundary"
                )

        # Check right boundary
        right_idx = idx + len(text)
        if right_idx < len(context):
            right_char = context[right_idx]
            if right_char.isalnum():
                return ValidationResult(
                    is_valid=False, rejection_reason="no_word_boundary"
                )

        return ValidationResult(is_valid=True)


class RFCEmailValidator(Validator):
    """
    Validates email format according to a simplified RFC 5322 pattern.
    """

    # Simplified email regex - covers most valid emails
    EMAIL_PATTERN = re.compile(
        r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    )

    def validate(
        self, text: str, entity_type: str, context: Optional[str] = None
    ) -> ValidationResult:
        # Only validate emails
        if entity_type != "email":
            return ValidationResult(is_valid=True)

        if self.EMAIL_PATTERN.match(text.strip()):
            return ValidationResult(is_valid=True)
        else:
            return ValidationResult(
                is_valid=False, rejection_reason="invalid_email_format"
            )


class MinDigitsValidator(Validator):
    """
    Validates that phone numbers have minimum required digits.

    Useful for distinguishing phones from other numeric strings.
    """

    def __init__(self, min_digits: int = 7):
        self.min_digits = min_digits

    def validate(
        self, text: str, entity_type: str, context: Optional[str] = None
    ) -> ValidationResult:
        # Only validate phone numbers
        if entity_type != "phone":
            return ValidationResult(is_valid=True)

        # Count only digits
        digit_count = sum(1 for c in text if c.isdigit())

        if digit_count < self.min_digits:
            return ValidationResult(is_valid=False, rejection_reason="too_few_digits")

        return ValidationResult(is_valid=True)


class ValidatorRegistry:
    """
    Registry that orchestrates validation across multiple validators.

    Runs universal validators first (labels, placeholders, length),
    then type-specific validators (Luhn, SSN, etc.).
    """

    def __init__(self):
        # Universal validators run for all types
        self.universal = [
            NotLabelValidator(),
            NotPlaceholderValidator(),
            MinLengthValidator(),
            BoundaryValidator(),
        ]

        # Type-specific validators
        self.type_validators = {
            "financial_account": [LuhnValidator(), CardPrefixValidator()],
            "credit_card": [LuhnValidator(), CardPrefixValidator()],
            "government_id": [SSNValidator(), AadhaarValidator()],
            "email": [RFCEmailValidator()],
            "phone": [MinDigitsValidator(7)],
        }

    def validate(
        self, text: str, entity_type: str, context: Optional[str] = None
    ) -> ValidationResult:
        """
        Run all applicable validators.

        Returns first rejection, or aggregates confidence adjustments on pass.
        """
        total_adjustment = 0.0

        # Run universal validators first
        for validator in self.universal:
            result = validator.validate(text, entity_type, context)
            if not result.is_valid:
                return result
            total_adjustment += result.confidence_adjustment

        # Run type-specific validators
        type_validators = self.type_validators.get(entity_type, [])
        for validator in type_validators:
            result = validator.validate(text, entity_type, context)
            if not result.is_valid:
                return result
            total_adjustment += result.confidence_adjustment

        return ValidationResult(is_valid=True, confidence_adjustment=total_adjustment)
