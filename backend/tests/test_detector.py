"""
Tests for the main PIIDetector class.

Tests the full detection pipeline:
- Entity detection (with mock entities for testing)
- Anonymization with session creation
- Restoration with session lookup or global search
"""

import os
import re
import tempfile
from dataclasses import dataclass
from typing import List

import pytest

from obscura.detector import PIIDetector, Entity, AnonymizeResult, RestoreResult


class TestEntity:
    """Tests for the Entity dataclass."""

    def test_entity_creation(self):
        """Entity can be created with all required fields."""
        entity = Entity(
            text="john@example.com",
            type="email",
            start=0,
            end=16,
            confidence=0.95,
        )

        assert entity.text == "john@example.com"
        assert entity.type == "email"
        assert entity.start == 0
        assert entity.end == 16
        assert entity.confidence == 0.95
        assert entity.source == "gliner"  # Default
        assert entity.validator_results == {}  # Default

    def test_entity_with_source_and_validator_results(self):
        """Entity can be created with custom source and validator results."""
        entity = Entity(
            text="4111111111111111",
            type="financial_account",
            start=10,
            end=26,
            confidence=0.9,
            source="user_correction",
            validator_results={"luhn": True, "prefix": "visa"},
        )

        assert entity.source == "user_correction"
        assert entity.validator_results == {"luhn": True, "prefix": "visa"}


class TestAnonymizeResult:
    """Tests for the AnonymizeResult dataclass."""

    def test_anonymize_result_creation(self):
        """AnonymizeResult can be created with all fields."""
        entity = Entity(
            text="test@example.com",
            type="email",
            start=0,
            end=16,
            confidence=0.9,
        )

        result = AnonymizeResult(
            session_id="abc123",
            anonymized_text="Contact [EMAIL_1] for details.",
            mappings={"[EMAIL_1]": "test@example.com"},
            entity_count=1,
            entities=[entity],
        )

        assert result.session_id == "abc123"
        assert "[EMAIL_1]" in result.anonymized_text
        assert result.mappings["[EMAIL_1]"] == "test@example.com"
        assert result.entity_count == 1
        assert len(result.entities) == 1


class TestRestoreResult:
    """Tests for the RestoreResult dataclass."""

    def test_restore_result_creation(self):
        """RestoreResult can be created with all fields."""
        result = RestoreResult(
            restored_text="Contact john@example.com for details.",
            mappings_applied=1,
            session_id="abc123",
        )

        assert "john@example.com" in result.restored_text
        assert result.mappings_applied == 1
        assert result.session_id == "abc123"

    def test_restore_result_without_session_id(self):
        """RestoreResult can be created without session_id."""
        result = RestoreResult(
            restored_text="Contact john@example.com for details.",
            mappings_applied=1,
        )

        assert result.session_id is None


class TestPIIDetectorInit:
    """Tests for PIIDetector initialization."""

    def test_init_creates_database(self):
        """PIIDetector creates database on initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            detector = PIIDetector(db_path=db_path, load_model=False)

            assert detector.db is not None
            assert os.path.exists(db_path)
            assert detector.validators is not None
            assert detector.context_analyzer is not None
            assert detector.corrections is not None
            assert detector.is_loaded is False
            assert detector.model is None

    def test_init_with_memory_db(self):
        """PIIDetector works with in-memory database."""
        detector = PIIDetector(db_path=":memory:", load_model=False)

        assert detector.db is not None
        # No file created for in-memory

    def test_init_without_model_loading(self):
        """PIIDetector can skip model loading for testing."""
        detector = PIIDetector(db_path=":memory:", load_model=False)

        assert detector.model is None
        assert detector.is_loaded is False


class TestPIIDetectorDetect:
    """Tests for the detect method."""

    def test_detect_with_mock_entities(self):
        """Detect method works with mock entities (bypasses GLiNER)."""
        detector = PIIDetector(db_path=":memory:", load_model=False)

        # Create mock entities matching GLiNER output format
        @dataclass
        class MockGLiNEREntity:
            text: str
            label: str
            start: int
            end: int
            score: float

        mock_entities = [
            MockGLiNEREntity(
                text="john@example.com",
                label="email",
                start=8,
                end=24,
                score=0.9,
            ),
        ]

        detector._mock_entities = mock_entities

        text = "Contact john@example.com for help."
        entities = detector.detect(text)

        assert len(entities) >= 1
        email_entity = next((e for e in entities if e.type == "email"), None)
        assert email_entity is not None
        assert email_entity.text == "john@example.com"

    def test_detect_empty_text_returns_empty_list(self):
        """Detect returns empty list for empty text."""
        detector = PIIDetector(db_path=":memory:", load_model=False)

        entities = detector.detect("")

        assert entities == []

    def test_detect_no_entities_returns_empty_list(self):
        """Detect returns empty list when no PII is found."""
        detector = PIIDetector(db_path=":memory:", load_model=False)
        detector._mock_entities = []

        entities = detector.detect("Hello world")

        assert entities == []


class TestPIIDetectorAnonymize:
    """Tests for the anonymize method."""

    def test_anonymize_without_entities(self):
        """Anonymize returns original text when no entities found."""
        detector = PIIDetector(db_path=":memory:", load_model=False)
        detector._mock_entities = []

        text = "Hello world, no PII here."
        result = detector.anonymize(text)

        assert result.anonymized_text == text
        assert result.entity_count == 0
        assert result.mappings == {}
        # Session should still be created
        assert result.session_id is not None

    def test_anonymize_creates_session(self):
        """Anonymize creates a session in the database."""
        detector = PIIDetector(db_path=":memory:", load_model=False)

        @dataclass
        class MockGLiNEREntity:
            text: str
            label: str
            start: int
            end: int
            score: float

        mock_entities = [
            MockGLiNEREntity(
                text="john@example.com",
                label="email",
                start=8,
                end=24,
                score=0.9,
            ),
        ]
        detector._mock_entities = mock_entities

        text = "Contact john@example.com for help."
        result = detector.anonymize(text)

        # Verify session was created
        session = detector.db.get_session(result.session_id)
        assert session is not None
        assert session["session_id"] == result.session_id
        assert "[EMAIL_1]" in result.anonymized_text
        assert result.mappings.get("[EMAIL_1]") == "john@example.com"

    def test_anonymize_replaces_entities_with_placeholders(self):
        """Anonymize replaces entities with [TYPE_N] placeholders."""
        detector = PIIDetector(db_path=":memory:", load_model=False)

        @dataclass
        class MockGLiNEREntity:
            text: str
            label: str
            start: int
            end: int
            score: float

        text = "John Smith can be reached at john@example.com or 555-123-4567."
        mock_entities = [
            MockGLiNEREntity(text="John Smith", label="person_name", start=0, end=10, score=0.85),
            MockGLiNEREntity(text="john@example.com", label="email", start=29, end=45, score=0.9),
            MockGLiNEREntity(text="555-123-4567", label="phone", start=49, end=61, score=0.88),
        ]
        detector._mock_entities = mock_entities

        result = detector.anonymize(text)

        # Check placeholders are present
        assert "[PERSON_NAME_1]" in result.anonymized_text
        assert "[EMAIL_1]" in result.anonymized_text
        assert "[PHONE_1]" in result.anonymized_text

        # Check original text is not present
        assert "John Smith" not in result.anonymized_text
        assert "john@example.com" not in result.anonymized_text
        assert "555-123-4567" not in result.anonymized_text

        # Check mappings
        assert result.mappings["[PERSON_NAME_1]"] == "John Smith"
        assert result.mappings["[EMAIL_1]"] == "john@example.com"
        assert result.mappings["[PHONE_1]"] == "555-123-4567"

    def test_anonymize_handles_multiple_same_type_entities(self):
        """Anonymize numbers placeholders for same type."""
        detector = PIIDetector(db_path=":memory:", load_model=False)

        @dataclass
        class MockGLiNEREntity:
            text: str
            label: str
            start: int
            end: int
            score: float

        text = "Contact alice@example.com or bob@example.com."
        mock_entities = [
            MockGLiNEREntity(text="alice@example.com", label="email", start=8, end=25, score=0.9),
            MockGLiNEREntity(text="bob@example.com", label="email", start=29, end=44, score=0.9),
        ]
        detector._mock_entities = mock_entities

        result = detector.anonymize(text)

        assert "[EMAIL_1]" in result.anonymized_text
        assert "[EMAIL_2]" in result.anonymized_text
        assert result.mappings.get("[EMAIL_1]") == "alice@example.com"
        assert result.mappings.get("[EMAIL_2]") == "bob@example.com"


class TestPIIDetectorRestore:
    """Tests for the restore method."""

    def test_restore_from_session(self):
        """Restore recovers original values using session_id."""
        detector = PIIDetector(db_path=":memory:", load_model=False)

        @dataclass
        class MockGLiNEREntity:
            text: str
            label: str
            start: int
            end: int
            score: float

        original_text = "Contact john@example.com for help."
        mock_entities = [
            MockGLiNEREntity(
                text="john@example.com",
                label="email",
                start=8,
                end=24,
                score=0.9,
            ),
        ]
        detector._mock_entities = mock_entities

        # Anonymize first
        anon_result = detector.anonymize(original_text)

        # Now restore
        restore_result = detector.restore(anon_result.anonymized_text, anon_result.session_id)

        assert restore_result.restored_text == original_text
        assert restore_result.mappings_applied == 1
        assert restore_result.session_id == anon_result.session_id

    def test_restore_global_without_session(self):
        """Restore finds mappings across all sessions when no session_id provided."""
        detector = PIIDetector(db_path=":memory:", load_model=False)

        @dataclass
        class MockGLiNEREntity:
            text: str
            label: str
            start: int
            end: int
            score: float

        # Create first session
        detector._mock_entities = [
            MockGLiNEREntity(text="alice@example.com", label="email", start=8, end=25, score=0.9),
        ]
        result1 = detector.anonymize("Contact alice@example.com for help.")

        # Create second session
        detector._mock_entities = [
            MockGLiNEREntity(text="bob@example.com", label="email", start=8, end=23, score=0.9),
        ]
        result2 = detector.anonymize("Contact bob@example.com today.")

        # Restore with a text that contains placeholders from both sessions
        combined_text = "Send to [EMAIL_1] and [EMAIL_1] from second."
        restore_result = detector.restore(combined_text)

        # Should find mappings without session_id
        assert restore_result.session_id is None
        # At least one mapping should be applied (the first [EMAIL_1] from either session)
        assert restore_result.mappings_applied >= 1

    def test_restore_handles_no_placeholders(self):
        """Restore handles text with no placeholders."""
        detector = PIIDetector(db_path=":memory:", load_model=False)

        text = "This text has no placeholders."
        result = detector.restore(text)

        assert result.restored_text == text
        assert result.mappings_applied == 0

    def test_restore_roundtrip(self):
        """Full roundtrip: original -> anonymize -> restore -> original."""
        detector = PIIDetector(db_path=":memory:", load_model=False)

        @dataclass
        class MockGLiNEREntity:
            text: str
            label: str
            start: int
            end: int
            score: float

        original_text = "My SSN is 123-45-6789 and email is test@example.com."
        mock_entities = [
            MockGLiNEREntity(text="123-45-6789", label="government_id", start=10, end=21, score=0.95),
            MockGLiNEREntity(text="test@example.com", label="email", start=35, end=51, score=0.9),
        ]
        detector._mock_entities = mock_entities

        # Anonymize
        anon_result = detector.anonymize(original_text)
        assert "123-45-6789" not in anon_result.anonymized_text
        assert "test@example.com" not in anon_result.anonymized_text

        # Restore
        restore_result = detector.restore(anon_result.anonymized_text, anon_result.session_id)
        assert restore_result.restored_text == original_text


class TestPIIDetectorConvenienceMethods:
    """Tests for convenience methods."""

    def test_get_stats(self):
        """get_stats returns database statistics."""
        detector = PIIDetector(db_path=":memory:", load_model=False)

        stats = detector.get_stats()

        assert "session_count" in stats
        assert "mapping_count" in stats
        assert "correction_count" in stats

    def test_cleanup(self):
        """cleanup runs database cleanup operations."""
        detector = PIIDetector(db_path=":memory:", load_model=False)

        # Should not raise
        detector.cleanup()

    def test_wipe_all(self):
        """wipe_all clears all database data."""
        detector = PIIDetector(db_path=":memory:", load_model=False)

        @dataclass
        class MockGLiNEREntity:
            text: str
            label: str
            start: int
            end: int
            score: float

        detector._mock_entities = [
            MockGLiNEREntity(text="test@example.com", label="email", start=8, end=24, score=0.9),
        ]
        detector.anonymize("Contact test@example.com for help.")

        # Verify data exists
        stats = detector.get_stats()
        assert stats["session_count"] == 1

        # Wipe
        result = detector.wipe_all()
        assert result["sessions_deleted"] == 1

        # Verify empty
        stats = detector.get_stats()
        assert stats["session_count"] == 0


class TestPIIDetectorValidation:
    """Tests for validation integration."""

    def test_invalid_entities_are_rejected(self):
        """Entities failing validation are filtered out."""
        detector = PIIDetector(db_path=":memory:", load_model=False)

        @dataclass
        class MockGLiNEREntity:
            text: str
            label: str
            start: int
            end: int
            score: float

        # "Email" is a label word and should be rejected by NotLabelValidator
        mock_entities = [
            MockGLiNEREntity(text="Email", label="person_name", start=0, end=5, score=0.8),
            MockGLiNEREntity(text="john@example.com", label="email", start=10, end=26, score=0.9),
        ]
        detector._mock_entities = mock_entities

        text = "Email me: john@example.com"
        entities = detector.detect(text)

        # "Email" should be filtered out, but "john@example.com" should remain
        texts = [e.text for e in entities]
        assert "Email" not in texts
        assert "john@example.com" in texts

    def test_placeholder_entities_are_rejected(self):
        """Existing placeholders are not re-detected as PII."""
        detector = PIIDetector(db_path=":memory:", load_model=False)

        @dataclass
        class MockGLiNEREntity:
            text: str
            label: str
            start: int
            end: int
            score: float

        # Simulate GLiNER detecting a placeholder
        mock_entities = [
            MockGLiNEREntity(text="[EMAIL_1]", label="email", start=8, end=17, score=0.7),
        ]
        detector._mock_entities = mock_entities

        text = "Contact [EMAIL_1] for help."
        entities = detector.detect(text)

        # Placeholder should be filtered out
        assert len(entities) == 0


class TestPIIDetectorEdgeCases:
    """Tests for edge cases."""

    def test_overlapping_entities(self):
        """Handles overlapping entities by keeping highest confidence."""
        detector = PIIDetector(db_path=":memory:", load_model=False)

        @dataclass
        class MockGLiNEREntity:
            text: str
            label: str
            start: int
            end: int
            score: float

        # Two entities that overlap
        mock_entities = [
            MockGLiNEREntity(text="John", label="person_name", start=0, end=4, score=0.7),
            MockGLiNEREntity(text="John Smith", label="person_name", start=0, end=10, score=0.9),
        ]
        detector._mock_entities = mock_entities

        text = "John Smith is here."
        entities = detector.detect(text)

        # Should keep the longer one with higher confidence
        assert len(entities) == 1
        assert entities[0].text == "John Smith"

    def test_entities_sorted_by_position(self):
        """Entities are returned sorted by start position."""
        detector = PIIDetector(db_path=":memory:", load_model=False)

        @dataclass
        class MockGLiNEREntity:
            text: str
            label: str
            start: int
            end: int
            score: float

        # Entities in random order
        mock_entities = [
            MockGLiNEREntity(text="phone", label="phone", start=30, end=42, score=0.8),
            MockGLiNEREntity(text="email", label="email", start=10, end=26, score=0.9),
            MockGLiNEREntity(text="name", label="person_name", start=0, end=4, score=0.85),
        ]
        detector._mock_entities = mock_entities

        text = "name email@test.com phone_number"
        entities = detector.detect(text)

        # Should be sorted by start position
        positions = [e.start for e in entities]
        assert positions == sorted(positions)
