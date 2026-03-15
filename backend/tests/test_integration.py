"""
Integration tests for the full PII detection pipeline.

These tests verify end-to-end functionality:
- User corrections persist across detector sessions
- Anonymize/restore roundtrip works correctly
- Validators properly filter invalid PII
- Confidence adjustments from validators are applied

Run with: python -m pytest tests/test_integration.py -v
"""

import os
import tempfile
from dataclasses import dataclass

import pytest

from obscura.detector import PIIDetector, Entity, AnonymizeResult, RestoreResult


@dataclass
class MockGLiNEREntity:
    """Mock entity matching GLiNER output format."""

    text: str
    label: str
    start: int
    end: int
    score: float


@pytest.fixture
def temp_db_path():
    """Create a temporary database file path."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)  # Close the file descriptor
    yield path
    # Cleanup
    if os.path.exists(path):
        os.unlink(path)


class TestRejectionPersistsAcrossSessions:
    """
    Test that user rejections are stored and applied in subsequent detections.

    Scenario:
    1. Detector 1: User rejects "Smith" as person_name (it's a company name)
    2. Detector 2: Opens same database, detects text with "Smith"
    3. Expectation: "Smith" should be filtered out in detector 2
    """

    def test_rejection_persists_across_sessions(self, temp_db_path):
        """User rejections should persist and apply in new detector sessions."""
        # Session 1: Add a rejection
        detector1 = PIIDetector(db_path=temp_db_path, load_model=False)

        # Add rejection for "Smith" detected as person_name
        detector1.corrections.add_rejection(
            text="Smith",
            detected_type="person_name",
            context_before="Company: ",
            context_after=" Industries",
        )

        # Verify rejection was stored
        correction = detector1.db.find_correction_by_text("Smith", "person_name")
        assert correction is not None
        assert correction["correction_kind"] == "reject"

        # Close detector1 by letting it go out of scope
        del detector1

        # Session 2: New detector with same database
        detector2 = PIIDetector(db_path=temp_db_path, load_model=False)

        # Mock GLiNER detecting "Smith" as person_name again
        text = "Contact Company: Smith Industries for support."
        mock_entities = [
            MockGLiNEREntity(text="Smith", label="person_name", start=17, end=22, score=0.75),
        ]
        detector2._mock_entities = mock_entities

        # Detect - "Smith" should be filtered out by the persisted rejection
        entities = detector2.detect(text)

        # Verify "Smith" was rejected
        entity_texts = [e.text for e in entities]
        assert "Smith" not in entity_texts

    def test_rejection_with_specific_context_persists(self, temp_db_path):
        """Rejections with specific context should work across sessions."""
        # Session 1: Reject "Email" as person_name (it's a label word)
        detector1 = PIIDetector(db_path=temp_db_path, load_model=False)
        detector1.corrections.add_rejection(
            text="Email",
            detected_type="person_name",
            context_before="",
            context_after=": ",
        )
        del detector1

        # Session 2: Detect text containing "Email" as a label
        detector2 = PIIDetector(db_path=temp_db_path, load_model=False)
        text = "Email: john@example.com"
        mock_entities = [
            MockGLiNEREntity(text="Email", label="person_name", start=0, end=5, score=0.7),
            MockGLiNEREntity(text="john@example.com", label="email", start=7, end=23, score=0.95),
        ]
        detector2._mock_entities = mock_entities

        entities = detector2.detect(text)

        # "Email" should be rejected, but "john@example.com" should remain
        texts = [e.text for e in entities]
        assert "Email" not in texts
        assert "john@example.com" in texts

    def test_multiple_rejections_persist(self, temp_db_path):
        """Multiple rejections should all persist and apply."""
        # Session 1: Add multiple rejections
        detector1 = PIIDetector(db_path=temp_db_path, load_model=False)
        detector1.corrections.add_rejection("Product", "person_name", "", "")
        detector1.corrections.add_rejection("Service", "person_name", "", "")
        detector1.corrections.add_rejection("Company", "person_name", "", "")
        del detector1

        # Session 2: Detect text with all three false positives
        detector2 = PIIDetector(db_path=temp_db_path, load_model=False)
        text = "Product and Service by Company Inc."
        mock_entities = [
            MockGLiNEREntity(text="Product", label="person_name", start=0, end=7, score=0.65),
            MockGLiNEREntity(text="Service", label="person_name", start=12, end=19, score=0.68),
            MockGLiNEREntity(text="Company", label="person_name", start=23, end=30, score=0.72),
        ]
        detector2._mock_entities = mock_entities

        entities = detector2.detect(text)

        # All three should be rejected
        assert len(entities) == 0


class TestAnonymizeRestoreRoundtrip:
    """
    Test that text can be anonymized and restored correctly.

    Scenario:
    1. Anonymize text with multiple PII entities
    2. Verify placeholders are correct
    3. Simulate LLM modification (preserve placeholders)
    4. Restore original values
    5. Verify text matches original
    """

    def test_anonymize_restore_roundtrip(self, temp_db_path):
        """Full anonymize -> LLM process -> restore cycle should preserve data."""
        detector = PIIDetector(db_path=temp_db_path, load_model=False)

        original_text = "Contact John Smith at john@example.com or call 555-123-4567."
        mock_entities = [
            MockGLiNEREntity(text="John Smith", label="person_name", start=8, end=18, score=0.9),
            MockGLiNEREntity(text="john@example.com", label="email", start=22, end=38, score=0.95),
            MockGLiNEREntity(text="555-123-4567", label="phone", start=47, end=59, score=0.88),
        ]
        detector._mock_entities = mock_entities

        # Anonymize
        anon_result = detector.anonymize(original_text)

        # Verify anonymization
        assert anon_result.entity_count == 3
        assert "[PERSON_NAME_1]" in anon_result.anonymized_text
        assert "[EMAIL_1]" in anon_result.anonymized_text
        assert "[PHONE_1]" in anon_result.anonymized_text
        assert "John Smith" not in anon_result.anonymized_text
        assert "john@example.com" not in anon_result.anonymized_text
        assert "555-123-4567" not in anon_result.anonymized_text

        # Simulate LLM response (preserving placeholders but changing text)
        llm_response = (
            "Thank you for contacting us. "
            "[PERSON_NAME_1] has been added to our system. "
            "We will send a confirmation to [EMAIL_1] and call [PHONE_1] soon."
        )

        # Restore using session_id
        restore_result = detector.restore(llm_response, anon_result.session_id)

        # Verify restoration
        assert restore_result.mappings_applied == 3
        assert "John Smith" in restore_result.restored_text
        assert "john@example.com" in restore_result.restored_text
        assert "555-123-4567" in restore_result.restored_text

    def test_roundtrip_preserves_exact_values(self, temp_db_path):
        """Restored values should exactly match originals."""
        detector = PIIDetector(db_path=temp_db_path, load_model=False)

        # Use text with special characters
        original_text = "Email: user+tag@example.com, SSN: 123-45-6789"
        mock_entities = [
            MockGLiNEREntity(text="user+tag@example.com", label="email", start=7, end=27, score=0.95),
            MockGLiNEREntity(text="123-45-6789", label="government_id", start=34, end=45, score=0.9),
        ]
        detector._mock_entities = mock_entities

        # Anonymize
        anon_result = detector.anonymize(original_text)

        # Restore (using the exact anonymized text)
        restore_result = detector.restore(anon_result.anonymized_text, anon_result.session_id)

        # Values should exactly match
        assert "user+tag@example.com" in restore_result.restored_text
        assert "123-45-6789" in restore_result.restored_text

    def test_roundtrip_with_multiple_same_type(self, temp_db_path):
        """Multiple entities of same type should each get unique placeholders."""
        detector = PIIDetector(db_path=temp_db_path, load_model=False)

        original_text = "Contact alice@example.com or bob@example.com"
        mock_entities = [
            MockGLiNEREntity(text="alice@example.com", label="email", start=8, end=25, score=0.95),
            MockGLiNEREntity(text="bob@example.com", label="email", start=29, end=44, score=0.92),
        ]
        detector._mock_entities = mock_entities

        # Anonymize
        anon_result = detector.anonymize(original_text)

        # Verify distinct placeholders
        assert "[EMAIL_1]" in anon_result.anonymized_text
        assert "[EMAIL_2]" in anon_result.anonymized_text
        assert anon_result.mappings["[EMAIL_1]"] == "alice@example.com"
        assert anon_result.mappings["[EMAIL_2]"] == "bob@example.com"

        # Restore
        restore_result = detector.restore(anon_result.anonymized_text, anon_result.session_id)

        # Both emails should be restored
        assert "alice@example.com" in restore_result.restored_text
        assert "bob@example.com" in restore_result.restored_text

    def test_roundtrip_across_sessions(self, temp_db_path):
        """Restoration should work even with a new detector instance."""
        # Session 1: Anonymize
        detector1 = PIIDetector(db_path=temp_db_path, load_model=False)
        original_text = "My email is test@example.com"
        mock_entities = [
            MockGLiNEREntity(text="test@example.com", label="email", start=12, end=28, score=0.95),
        ]
        detector1._mock_entities = mock_entities

        anon_result = detector1.anonymize(original_text)
        session_id = anon_result.session_id
        del detector1

        # Session 2: Restore
        detector2 = PIIDetector(db_path=temp_db_path, load_model=False)
        restore_result = detector2.restore(anon_result.anonymized_text, session_id)

        assert restore_result.restored_text == original_text


class TestValidationRejectsInvalidSSN:
    """
    Test that invalid SSNs don't get boosted confidence.

    SSN validation rules:
    - Area (first 3 digits) cannot be 000, 666, or 900-999
    - Group (middle 2 digits) cannot be 00
    - Serial (last 4 digits) cannot be 0000
    """

    def test_validation_rejects_invalid_ssn(self, temp_db_path):
        """Invalid SSNs should be rejected by validators."""
        detector = PIIDetector(db_path=temp_db_path, load_model=False)

        # Test invalid area number (000)
        text = "SSN: 000-45-6789"
        mock_entities = [
            MockGLiNEREntity(text="000-45-6789", label="government_id", start=5, end=16, score=0.8),
        ]
        detector._mock_entities = mock_entities

        entities = detector.detect(text)

        # Invalid SSN should be filtered out
        assert len(entities) == 0

    def test_rejects_ssn_area_666(self, temp_db_path):
        """SSN with area 666 should be rejected."""
        detector = PIIDetector(db_path=temp_db_path, load_model=False)

        text = "SSN: 666-45-6789"
        mock_entities = [
            MockGLiNEREntity(text="666-45-6789", label="government_id", start=5, end=16, score=0.8),
        ]
        detector._mock_entities = mock_entities

        entities = detector.detect(text)
        assert len(entities) == 0

    def test_rejects_ssn_area_900_plus(self, temp_db_path):
        """SSN with area 900-999 should be rejected."""
        detector = PIIDetector(db_path=temp_db_path, load_model=False)

        for area in ["900", "950", "999"]:
            text = f"SSN: {area}-45-6789"
            mock_entities = [
                MockGLiNEREntity(text=f"{area}-45-6789", label="government_id", start=5, end=16, score=0.8),
            ]
            detector._mock_entities = mock_entities

            entities = detector.detect(text)
            assert len(entities) == 0, f"Area {area} should be rejected"

    def test_rejects_ssn_group_00(self, temp_db_path):
        """SSN with group 00 should be rejected."""
        detector = PIIDetector(db_path=temp_db_path, load_model=False)

        text = "SSN: 123-00-6789"
        mock_entities = [
            MockGLiNEREntity(text="123-00-6789", label="government_id", start=5, end=16, score=0.8),
        ]
        detector._mock_entities = mock_entities

        entities = detector.detect(text)
        assert len(entities) == 0

    def test_rejects_ssn_serial_0000(self, temp_db_path):
        """SSN with serial 0000 should be rejected."""
        detector = PIIDetector(db_path=temp_db_path, load_model=False)

        text = "SSN: 123-45-0000"
        mock_entities = [
            MockGLiNEREntity(text="123-45-0000", label="government_id", start=5, end=16, score=0.8),
        ]
        detector._mock_entities = mock_entities

        entities = detector.detect(text)
        assert len(entities) == 0

    def test_rejects_known_invalid_woolworth_ssn(self, temp_db_path):
        """Famous Woolworth SSN (078-05-1120) should be rejected."""
        detector = PIIDetector(db_path=temp_db_path, load_model=False)

        text = "SSN: 078-05-1120"
        mock_entities = [
            MockGLiNEREntity(text="078-05-1120", label="government_id", start=5, end=16, score=0.8),
        ]
        detector._mock_entities = mock_entities

        entities = detector.detect(text)
        assert len(entities) == 0

    def test_accepts_valid_ssn(self, temp_db_path):
        """Valid SSN should be accepted and get confidence boost."""
        detector = PIIDetector(db_path=temp_db_path, load_model=False)

        text = "SSN: 123-45-6789"
        mock_entities = [
            MockGLiNEREntity(text="123-45-6789", label="government_id", start=5, end=16, score=0.7),
        ]
        detector._mock_entities = mock_entities

        entities = detector.detect(text)

        # Valid SSN should pass through
        assert len(entities) == 1
        assert entities[0].text == "123-45-6789"


class TestValidationAcceptsValidCreditCard:
    """
    Test that valid credit cards (passing Luhn) get confidence boost.

    Credit card validation:
    - Must pass Luhn checksum
    - Must have recognized prefix (Visa, MasterCard, Amex, Discover)
    - Valid cards get confidence boost (~0.3)
    """

    def test_validation_accepts_valid_credit_card(self, temp_db_path):
        """Valid credit card (Luhn-passing) should be accepted with confidence boost."""
        detector = PIIDetector(db_path=temp_db_path, load_model=False)

        # Valid Visa card: 4532015112830366 (passes Luhn)
        text = "Card: 4532015112830366"
        mock_entities = [
            MockGLiNEREntity(text="4532015112830366", label="financial_account", start=6, end=22, score=0.7),
        ]
        detector._mock_entities = mock_entities

        entities = detector.detect(text)

        # Valid card should pass through
        assert len(entities) == 1
        assert entities[0].text == "4532015112830366"

    def test_rejects_invalid_luhn_checksum(self, temp_db_path):
        """Credit card with invalid Luhn checksum should be rejected."""
        detector = PIIDetector(db_path=temp_db_path, load_model=False)

        # Invalid: last digit changed (should fail Luhn)
        text = "Card: 4532015112830367"
        mock_entities = [
            MockGLiNEREntity(text="4532015112830367", label="financial_account", start=6, end=22, score=0.85),
        ]
        detector._mock_entities = mock_entities

        entities = detector.detect(text)

        # Invalid card should be filtered out
        assert len(entities) == 0

    def test_accepts_formatted_card_with_dashes(self, temp_db_path):
        """Credit card with formatting (dashes) should still validate."""
        detector = PIIDetector(db_path=temp_db_path, load_model=False)

        # Valid Visa with dashes
        text = "Card: 4532-0151-1283-0366"
        mock_entities = [
            MockGLiNEREntity(text="4532-0151-1283-0366", label="financial_account", start=6, end=25, score=0.75),
        ]
        detector._mock_entities = mock_entities

        entities = detector.detect(text)

        assert len(entities) == 1

    def test_accepts_formatted_card_with_spaces(self, temp_db_path):
        """Credit card with spaces should still validate."""
        detector = PIIDetector(db_path=temp_db_path, load_model=False)

        # Valid Visa with spaces
        text = "Card: 4532 0151 1283 0366"
        mock_entities = [
            MockGLiNEREntity(text="4532 0151 1283 0366", label="financial_account", start=6, end=25, score=0.75),
        ]
        detector._mock_entities = mock_entities

        entities = detector.detect(text)

        assert len(entities) == 1

    def test_accepts_mastercard(self, temp_db_path):
        """Valid MasterCard should be accepted."""
        detector = PIIDetector(db_path=temp_db_path, load_model=False)

        # Valid MasterCard: 5425233430109903
        text = "Card: 5425233430109903"
        mock_entities = [
            MockGLiNEREntity(text="5425233430109903", label="financial_account", start=6, end=22, score=0.75),
        ]
        detector._mock_entities = mock_entities

        entities = detector.detect(text)

        assert len(entities) == 1
        assert entities[0].text == "5425233430109903"

    def test_accepts_amex(self, temp_db_path):
        """Valid American Express card should be accepted."""
        detector = PIIDetector(db_path=temp_db_path, load_model=False)

        # Valid Amex: 378282246310005
        text = "Card: 378282246310005"
        mock_entities = [
            MockGLiNEREntity(text="378282246310005", label="financial_account", start=6, end=21, score=0.75),
        ]
        detector._mock_entities = mock_entities

        entities = detector.detect(text)

        assert len(entities) == 1

    def test_rejects_unknown_card_prefix(self, temp_db_path):
        """Card with unknown prefix should be rejected."""
        detector = PIIDetector(db_path=temp_db_path, load_model=False)

        # Invalid prefix (starts with 1)
        text = "Card: 1234567890123456"
        mock_entities = [
            MockGLiNEREntity(text="1234567890123456", label="financial_account", start=6, end=22, score=0.75),
        ]
        detector._mock_entities = mock_entities

        entities = detector.detect(text)

        # Should be rejected due to unknown prefix
        assert len(entities) == 0


class TestMixedValidationScenarios:
    """Test complex scenarios with multiple validation rules."""

    def test_mixed_valid_and_invalid_pii(self, temp_db_path):
        """Mix of valid and invalid PII should be correctly filtered."""
        detector = PIIDetector(db_path=temp_db_path, load_model=False)

        # Text with valid email, invalid SSN, valid credit card
        text = "Email: john@example.com, SSN: 000-12-3456, Card: 4532015112830366"
        mock_entities = [
            MockGLiNEREntity(text="john@example.com", label="email", start=7, end=23, score=0.95),
            MockGLiNEREntity(text="000-12-3456", label="government_id", start=30, end=41, score=0.8),
            MockGLiNEREntity(text="4532015112830366", label="financial_account", start=49, end=65, score=0.85),
        ]
        detector._mock_entities = mock_entities

        entities = detector.detect(text)

        # Only valid entities should pass
        texts = [e.text for e in entities]
        assert "john@example.com" in texts  # Valid email
        assert "000-12-3456" not in texts   # Invalid SSN (area 000)
        assert "4532015112830366" in texts  # Valid credit card

    def test_label_words_rejected_before_type_validation(self, temp_db_path):
        """Label words should be rejected before type-specific validation."""
        detector = PIIDetector(db_path=temp_db_path, load_model=False)

        text = "Email address goes here"
        mock_entities = [
            MockGLiNEREntity(text="Email", label="person_name", start=0, end=5, score=0.65),
        ]
        detector._mock_entities = mock_entities

        entities = detector.detect(text)

        # "Email" should be rejected as a label word
        assert len(entities) == 0

    def test_placeholders_not_redetected(self, temp_db_path):
        """Placeholder patterns should not be detected as new PII."""
        detector = PIIDetector(db_path=temp_db_path, load_model=False)

        # Text that already has placeholders
        text = "Contact [EMAIL_1] at [PHONE_1]"
        mock_entities = [
            MockGLiNEREntity(text="[EMAIL_1]", label="email", start=8, end=17, score=0.7),
            MockGLiNEREntity(text="[PHONE_1]", label="phone", start=21, end=30, score=0.7),
        ]
        detector._mock_entities = mock_entities

        entities = detector.detect(text)

        # Placeholders should be rejected
        assert len(entities) == 0


class TestCorrectionWithValidation:
    """Test that corrections work together with validation."""

    def test_relabel_persists_and_applies(self, temp_db_path):
        """Relabel corrections should persist and change entity types."""
        # Session 1: Add relabel correction
        detector1 = PIIDetector(db_path=temp_db_path, load_model=False)
        detector1.corrections.add_relabel(
            text="123-45-6789",
            original_type="phone",
            corrected_type="government_id",
            context_before="SSN: ",
            context_after="",
        )
        del detector1

        # Session 2: Detect with wrong type
        detector2 = PIIDetector(db_path=temp_db_path, load_model=False)
        text = "SSN: 123-45-6789"
        mock_entities = [
            MockGLiNEREntity(text="123-45-6789", label="phone", start=5, end=16, score=0.75),
        ]
        detector2._mock_entities = mock_entities

        entities = detector2.detect(text)

        # Type should be corrected to government_id
        assert len(entities) == 1
        assert entities[0].type == "government_id"

    def test_missed_pii_persists_and_applies(self, temp_db_path):
        """Missed PII corrections should find patterns in future documents.

        Note: The corrections layer only runs when GLiNER finds at least one entity.
        This tests that when GLiNER finds something, missed PII patterns are also found.
        """
        # Session 1: Add missed PII
        detector1 = PIIDetector(db_path=temp_db_path, load_model=False)
        detector1.corrections.add_missed_pii(
            text="ACCT-12345",
            entity_type="reference_number",
            context_before="Account: ",
            context_after="",
        )
        del detector1

        # Session 2: Detect text containing the missed pattern AND another entity
        # The corrections layer runs only when GLiNER finds at least one entity
        detector2 = PIIDetector(db_path=temp_db_path, load_model=False)
        text = "Account: ACCT-12345 is active. Email: test@example.com"
        detector2._mock_entities = [
            MockGLiNEREntity(text="test@example.com", label="email", start=38, end=54, score=0.95),
        ]

        entities = detector2.detect(text)

        # Both the GLiNER-detected email and the missed PII should be found
        texts = [e.text for e in entities]
        assert "test@example.com" in texts  # GLiNER detected
        assert "ACCT-12345" in texts  # Missed PII found by corrections

        # Verify the missed PII has correct type
        acct_entity = next(e for e in entities if e.text == "ACCT-12345")
        assert acct_entity.type == "reference_number"


class TestCleanupAndStats:
    """Test cleanup and statistics across sessions."""

    def test_stats_persist_across_sessions(self, temp_db_path):
        """Database stats should be accurate across sessions."""
        # Session 1: Create some data
        detector1 = PIIDetector(db_path=temp_db_path, load_model=False)
        detector1._mock_entities = [
            MockGLiNEREntity(text="test@example.com", label="email", start=0, end=16, score=0.9),
        ]
        detector1.anonymize("test@example.com")
        detector1.corrections.add_rejection("Test", "person_name", "", "")
        del detector1

        # Session 2: Check stats
        detector2 = PIIDetector(db_path=temp_db_path, load_model=False)
        stats = detector2.get_stats()

        assert stats["session_count"] == 1
        assert stats["correction_count"] == 1
        assert stats["mapping_count"] >= 1

    def test_wipe_clears_all_data(self, temp_db_path):
        """Wipe should clear all data."""
        # Create some data
        detector = PIIDetector(db_path=temp_db_path, load_model=False)
        detector._mock_entities = [
            MockGLiNEREntity(text="test@example.com", label="email", start=0, end=16, score=0.9),
        ]
        detector.anonymize("test@example.com")
        detector.corrections.add_rejection("Test", "person_name", "", "")

        # Verify data exists
        stats = detector.get_stats()
        assert stats["session_count"] == 1
        assert stats["correction_count"] == 1

        # Wipe
        result = detector.wipe_all()
        assert result["sessions_deleted"] >= 1

        # Verify data is gone
        stats = detector.get_stats()
        assert stats["session_count"] == 0
