"""
Tests for the user correction layer.

Run with: python -m pytest tests/test_corrections.py -v
"""

from dataclasses import dataclass
from typing import Optional

import pytest

from obscura.database import DatabaseManager
from obscura.corrections import CorrectionLayer, CorrectedEntity


@dataclass
class MockEntity:
    """Mock entity for testing."""

    text: str
    label: str
    start: int
    end: int
    score: float


@pytest.fixture
def db():
    """Create an in-memory database for testing."""
    return DatabaseManager(":memory:")


@pytest.fixture
def correction_layer(db):
    """Create a correction layer with the database."""
    return CorrectionLayer(db)


class TestCorrectedEntityDataclass:
    """Tests for the CorrectedEntity dataclass."""

    def test_corrected_entity_creation(self):
        """Should create a CorrectedEntity with all fields."""
        entity = CorrectedEntity(
            text="john@example.com",
            type="email",
            start=10,
            end=26,
            confidence=0.95,
            source="user_correction",
        )

        assert entity.text == "john@example.com"
        assert entity.type == "email"
        assert entity.start == 10
        assert entity.end == 26
        assert entity.confidence == 0.95
        assert entity.source == "user_correction"

    def test_corrected_entity_default_source(self):
        """Should have default source='user_correction'."""
        entity = CorrectedEntity(
            text="test",
            type="email",
            start=0,
            end=4,
            confidence=1.0,
        )

        assert entity.source == "user_correction"


class TestRejection:
    """Tests for rejection corrections."""

    def test_rejection_removes_entity(self, correction_layer, db):
        """Adding rejection for a detected entity should filter it out."""
        # Add a rejection: "Email" detected as person_name is NOT PII
        correction_layer.add_rejection(
            text="Email",
            detected_type="person_name",
            context_before="Contact: ",
            context_after=" Address",
        )

        # Create entities that include the false positive
        entities = [
            MockEntity(text="Email", label="person_name", start=9, end=14, score=0.75),
            MockEntity(text="john@example.com", label="email", start=16, end=32, score=0.95),
        ]

        # Apply corrections
        full_text = "Contact: Email Address: john@example.com"
        result = correction_layer.apply_corrections(entities, full_text)

        # "Email" should be filtered out
        result_texts = [e.text for e in result]
        assert "Email" not in result_texts
        assert "john@example.com" in result_texts

    def test_rejection_with_matching_context(self, correction_layer, db):
        """Rejection should match based on context when text is ambiguous."""
        # Add rejection for "Smith" in specific context
        correction_layer.add_rejection(
            text="Smith",
            detected_type="person_name",
            context_before="Company: ",
            context_after=" & Co",
        )

        # This "Smith" is a company name, not a person
        entities = [
            MockEntity(text="Smith", label="person_name", start=9, end=14, score=0.8),
        ]

        full_text = "Company: Smith & Co, LLC"
        result = correction_layer.apply_corrections(entities, full_text)

        # Should be filtered out due to context match
        assert len(result) == 0


class TestRelabel:
    """Tests for relabel corrections."""

    def test_relabel_changes_type(self, correction_layer, db):
        """Adding relabel correction should change entity type."""
        # Add relabel: "123-45-6789" was detected as phone but is actually SSN
        correction_layer.add_relabel(
            text="123-45-6789",
            original_type="phone",
            corrected_type="government_id",
            context_before="SSN: ",
            context_after="",
        )

        entities = [
            MockEntity(text="123-45-6789", label="phone", start=5, end=16, score=0.7),
        ]

        full_text = "SSN: 123-45-6789"
        result = correction_layer.apply_corrections(entities, full_text)

        # Type should be changed to government_id
        assert len(result) == 1
        assert result[0].type == "government_id"

    def test_relabel_preserves_other_fields(self, correction_layer, db):
        """Relabel should preserve start, end, and text."""
        correction_layer.add_relabel(
            text="test@test.com",
            original_type="digital_id",
            corrected_type="email",
            context_before="",
            context_after="",
        )

        entities = [
            MockEntity(text="test@test.com", label="digital_id", start=0, end=13, score=0.85),
        ]

        result = correction_layer.apply_corrections(entities, "test@test.com")

        assert len(result) == 1
        assert result[0].text == "test@test.com"
        assert result[0].start == 0
        assert result[0].end == 13
        assert result[0].type == "email"


class TestMissedPII:
    """Tests for missed PII corrections."""

    def test_add_missed_finds_pii(self, correction_layer, db):
        """Adding missed PII should find it in text."""
        # User says GLiNER missed this SSN
        correction_layer.add_missed_pii(
            text="111-22-3333",
            entity_type="government_id",
            context_before="My SSN is ",
            context_after=" please",
        )

        # GLiNER found nothing
        entities = []

        full_text = "My SSN is 111-22-3333 please process it"
        result = correction_layer.apply_corrections(entities, full_text)

        # Should find the missed SSN
        assert len(result) == 1
        assert result[0].text == "111-22-3333"
        assert result[0].type == "government_id"
        assert result[0].source == "user_correction"
        assert result[0].start == 10
        assert result[0].end == 21

    def test_missed_pii_multiple_occurrences(self, correction_layer, db):
        """Should find all occurrences of missed PII."""
        correction_layer.add_missed_pii(
            text="secret123",
            entity_type="digital_id",
            context_before="",
            context_after="",
        )

        entities = []
        full_text = "Password: secret123, Confirm: secret123"
        result = correction_layer.apply_corrections(entities, full_text)

        # Should find both occurrences
        assert len(result) == 2
        assert all(e.text == "secret123" for e in result)
        assert all(e.type == "digital_id" for e in result)

    def test_missed_pii_not_duplicate(self, correction_layer, db):
        """Should not add missed PII if already detected."""
        correction_layer.add_missed_pii(
            text="john@example.com",
            entity_type="email",
            context_before="",
            context_after="",
        )

        # GLiNER already found this
        entities = [
            MockEntity(text="john@example.com", label="email", start=0, end=16, score=0.99),
        ]

        full_text = "john@example.com"
        result = correction_layer.apply_corrections(entities, full_text)

        # Should not duplicate
        assert len(result) == 1


class TestBoundaryFix:
    """Tests for boundary fix corrections."""

    def test_boundary_fix_expands_entity(self, correction_layer, db):
        """User fixes '123 Main' to '123 Main St, New York'."""
        correction_layer.add_boundary_fix(
            original_text="123 Main",
            corrected_text="123 Main St, New York",
            entity_type="address",
            context_before="Address: ",
            context_after=" NY 10001",
        )

        entities = [
            MockEntity(text="123 Main", label="address", start=9, end=17, score=0.7),
        ]

        full_text = "Address: 123 Main St, New York NY 10001"
        result = correction_layer.apply_corrections(entities, full_text)

        # Should expand to full address
        assert len(result) == 1
        assert result[0].text == "123 Main St, New York"
        assert result[0].type == "address"

    def test_boundary_fix_contracts_entity(self, correction_layer, db):
        """User fixes 'John Smith, CEO' to just 'John Smith'."""
        correction_layer.add_boundary_fix(
            original_text="John Smith, CEO",
            corrected_text="John Smith",
            entity_type="person_name",
            context_before="Contact ",
            context_after=" at",
        )

        entities = [
            MockEntity(text="John Smith, CEO", label="person_name", start=8, end=23, score=0.8),
        ]

        full_text = "Contact John Smith, CEO at john@example.com"
        result = correction_layer.apply_corrections(entities, full_text)

        assert len(result) == 1
        assert result[0].text == "John Smith"

    def test_boundary_fix_updates_positions(self, correction_layer, db):
        """Boundary fix should update start/end positions."""
        correction_layer.add_boundary_fix(
            original_text="123",
            corrected_text="123 Oak Street",
            entity_type="address",
            context_before="Lives at ",
            context_after=" Apt 5",
        )

        entities = [
            MockEntity(text="123", label="address", start=9, end=12, score=0.6),
        ]

        full_text = "Lives at 123 Oak Street Apt 5"
        result = correction_layer.apply_corrections(entities, full_text)

        assert len(result) == 1
        assert result[0].start == 9
        assert result[0].end == 23  # 9 + len("123 Oak Street")


class TestPassthrough:
    """Tests for entities without matching corrections."""

    def test_no_correction_passes_through(self, correction_layer, db):
        """Without matching correction, entity passes unchanged."""
        # No corrections added
        entities = [
            MockEntity(text="john@example.com", label="email", start=0, end=16, score=0.95),
            MockEntity(text="555-1234", label="phone", start=20, end=28, score=0.85),
        ]

        full_text = "john@example.com or 555-1234"
        result = correction_layer.apply_corrections(entities, full_text)

        # All entities should pass through
        assert len(result) == 2
        result_texts = [e.text for e in result]
        assert "john@example.com" in result_texts
        assert "555-1234" in result_texts

    def test_unrelated_correction_does_not_affect_entity(self, correction_layer, db):
        """Correction for different text should not affect unrelated entity."""
        correction_layer.add_rejection(
            text="Company",
            detected_type="person_name",
            context_before="",
            context_after="",
        )

        entities = [
            MockEntity(text="John Doe", label="person_name", start=0, end=8, score=0.9),
        ]

        result = correction_layer.apply_corrections(entities, "John Doe is here")

        assert len(result) == 1
        assert result[0].text == "John Doe"


class TestAppliedCountTracking:
    """Tests for tracking correction usage."""

    def test_increment_applied_count(self, correction_layer, db):
        """Verify correction usage is tracked."""
        # Add a rejection
        correction_layer.add_rejection(
            text="Test",
            detected_type="person_name",
            context_before="",
            context_after="",
        )

        entities = [
            MockEntity(text="Test", label="person_name", start=0, end=4, score=0.7),
        ]

        # Apply corrections multiple times
        correction_layer.apply_corrections(entities, "Test")
        correction_layer.apply_corrections(entities, "Test")
        correction_layer.apply_corrections(entities, "Test")

        # Check the correction was tracked
        correction = db.find_correction_by_text("Test", "person_name")
        assert correction["times_applied"] == 3

    def test_increment_for_relabel(self, correction_layer, db):
        """Relabel corrections should also track usage."""
        correction_layer.add_relabel(
            text="12345",
            original_type="phone",
            corrected_type="reference_number",
            context_before="Order #",
            context_after="",
        )

        entities = [
            MockEntity(text="12345", label="phone", start=7, end=12, score=0.6),
        ]

        correction_layer.apply_corrections(entities, "Order #12345")

        correction = db.find_correction_by_text("12345", "phone")
        assert correction["times_applied"] == 1


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_entities_list(self, correction_layer, db):
        """Should handle empty entity list gracefully."""
        result = correction_layer.apply_corrections([], "Some text here")
        assert result == []

    def test_empty_text(self, correction_layer, db):
        """Should handle empty text gracefully."""
        entities = [
            MockEntity(text="test", label="email", start=0, end=4, score=0.9),
        ]

        result = correction_layer.apply_corrections(entities, "")
        # With empty text, nothing matches
        assert len(result) == 0

    def test_case_insensitive_text_matching(self, correction_layer, db):
        """Correction matching should be case-insensitive."""
        correction_layer.add_rejection(
            text="EMAIL",
            detected_type="person_name",
            context_before="",
            context_after="",
        )

        entities = [
            MockEntity(text="email", label="person_name", start=0, end=5, score=0.7),
        ]

        result = correction_layer.apply_corrections(entities, "email")

        # Should match despite case difference
        assert len(result) == 0

    def test_overlapping_entities_handled(self, correction_layer, db):
        """Should handle overlapping entity positions - missed PII not added if overlaps."""
        # Add missed PII that overlaps with existing detection
        correction_layer.add_missed_pii(
            text="john.doe@company.com",
            entity_type="email",
            context_before="",
            context_after="",
        )

        entities = [
            # GLiNER only detected "john.doe" - this overlaps with the full email
            MockEntity(text="john.doe", label="person_name", start=0, end=8, score=0.8),
        ]

        full_text = "john.doe@company.com"
        result = correction_layer.apply_corrections(entities, full_text)

        # The missed PII (0,20) overlaps with detected entity (0,8)
        # So only the GLiNER-detected entity should remain
        # This is correct behavior - we don't want duplicate overlapping entities
        assert len(result) == 1
        assert result[0].text == "john.doe"

    def test_non_overlapping_missed_pii_added(self, correction_layer, db):
        """Should add missed PII when it doesn't overlap with detected entities."""
        correction_layer.add_missed_pii(
            text="secret123",
            entity_type="digital_id",
            context_before="",
            context_after="",
        )

        entities = [
            # GLiNER detected email at different position
            MockEntity(text="john@test.com", label="email", start=0, end=13, score=0.95),
        ]

        full_text = "john@test.com and secret123"
        result = correction_layer.apply_corrections(entities, full_text)

        # Should have both: the email and the missed secret
        assert len(result) == 2
        result_texts = [e.text for e in result]
        assert "john@test.com" in result_texts
        assert "secret123" in result_texts

    def test_correction_with_special_characters(self, correction_layer, db):
        """Should handle special characters in correction text."""
        correction_layer.add_missed_pii(
            text="user+tag@example.com",
            entity_type="email",
            context_before="",
            context_after="",
        )

        entities = []
        full_text = "Contact: user+tag@example.com"
        result = correction_layer.apply_corrections(entities, full_text)

        assert len(result) == 1
        assert result[0].text == "user+tag@example.com"

    def test_multiple_correction_types_combined(self, correction_layer, db):
        """Should apply rejections, relabels, and missed PII together."""
        # Reject "Email" as person_name
        correction_layer.add_rejection(
            text="Email",
            detected_type="person_name",
            context_before="",
            context_after=":",
        )

        # Relabel "123456" from phone to reference_number
        correction_layer.add_relabel(
            text="123456",
            original_type="phone",
            corrected_type="reference_number",
            context_before="Order ",
            context_after="",
        )

        # Add missed SSN
        correction_layer.add_missed_pii(
            text="999-88-7777",
            entity_type="government_id",
            context_before="SSN: ",
            context_after="",
        )

        entities = [
            MockEntity(text="Email", label="person_name", start=0, end=5, score=0.7),
            MockEntity(text="123456", label="phone", start=18, end=24, score=0.8),
            MockEntity(text="john@test.com", label="email", start=44, end=57, score=0.95),
        ]

        # Positions: Email=0-5, Order=13, 123456=18-24, SSN:=26, 999-88-7777=31-42, john@test.com=44-57
        full_text = "Email: test, Order 123456, SSN: 999-88-7777, john@test.com"
        result = correction_layer.apply_corrections(entities, full_text)

        # Email (person_name) should be rejected
        # 123456 should be relabeled to reference_number
        # 999-88-7777 should be added as government_id
        # john@test.com should pass through

        result_by_text = {e.text: e for e in result}

        assert "Email" not in result_by_text
        assert result_by_text["123456"].type == "reference_number"
        assert result_by_text["999-88-7777"].type == "government_id"
        assert result_by_text["john@test.com"].type == "email"


class TestUserFacingMethods:
    """Tests for the user-facing API methods."""

    def test_add_rejection_stores_correctly(self, correction_layer, db):
        """add_rejection should store with correct correction_kind."""
        correction_layer.add_rejection(
            text="Test",
            detected_type="person_name",
            context_before="before",
            context_after="after",
        )

        correction = db.find_correction_by_text("Test", "person_name")
        assert correction is not None
        assert correction["correction_kind"] == "reject"
        assert correction["original_type"] == "person_name"

    def test_add_relabel_stores_correctly(self, correction_layer, db):
        """add_relabel should store both original and corrected types."""
        correction_layer.add_relabel(
            text="12345",
            original_type="phone",
            corrected_type="reference_number",
            context_before="",
            context_after="",
        )

        correction = db.find_correction_by_text("12345", "phone")
        assert correction is not None
        assert correction["correction_kind"] == "relabel"
        assert correction["original_type"] == "phone"
        assert correction["corrected_type"] == "reference_number"

    def test_add_boundary_fix_stores_correctly(self, correction_layer, db):
        """add_boundary_fix should store original and corrected text."""
        correction_layer.add_boundary_fix(
            original_text="123 Main",
            corrected_text="123 Main Street",
            entity_type="address",
            context_before="",
            context_after="",
        )

        correction = db.find_correction_by_text("123 Main", "address")
        assert correction is not None
        assert correction["correction_kind"] == "boundary"
        assert correction["original_text"] == "123 Main"
        assert correction["corrected_text"] == "123 Main Street"

    def test_add_missed_pii_stores_correctly(self, correction_layer, db):
        """add_missed_pii should store with correct correction_kind."""
        correction_layer.add_missed_pii(
            text="secret-value",
            entity_type="digital_id",
            context_before="",
            context_after="",
        )

        # For add_missed, original_type is None, so search without type filter
        correction = db.find_correction_by_text("secret-value")
        assert correction is not None
        assert correction["correction_kind"] == "add_missed"
        assert correction["corrected_type"] == "digital_id"
        # original_type should be None for add_missed
        assert correction["original_type"] is None
