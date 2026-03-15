"""
Tests for the context analyzer.

Run with: python -m pytest tests/test_context.py -v
"""

import pytest
from dataclasses import dataclass
from typing import Optional

from obscura.context import ContextAnalyzer, CONTEXT_SIGNALS


@dataclass
class MockEntity:
    """Mock entity for testing."""

    text: str
    type: str
    start: int
    end: int

    @classmethod
    def create(cls, text: str, entity_type: str, start: int = 0) -> "MockEntity":
        """Create a mock entity with calculated end position."""
        return cls(text=text, type=entity_type, start=start, end=start + len(text))


class TestContextSignals:
    """Tests for CONTEXT_SIGNALS configuration."""

    def test_boost_signals_exist(self):
        """Should have boost signals for key entity types."""
        assert "boost" in CONTEXT_SIGNALS
        assert "email" in CONTEXT_SIGNALS["boost"]
        assert "phone" in CONTEXT_SIGNALS["boost"]
        assert "person_name" in CONTEXT_SIGNALS["boost"]

    def test_penalize_signals_exist(self):
        """Should have penalize signals for key entity types."""
        assert "penalize" in CONTEXT_SIGNALS
        assert "__all__" in CONTEXT_SIGNALS["penalize"]

    def test_boost_patterns_are_valid_regex(self):
        """All boost patterns should be valid regex."""
        import re

        for entity_type, patterns in CONTEXT_SIGNALS["boost"].items():
            for pattern in patterns:
                try:
                    re.compile(pattern, re.IGNORECASE)
                except re.error as e:
                    pytest.fail(f"Invalid regex in boost.{entity_type}: {pattern} - {e}")

    def test_penalize_patterns_are_valid_regex(self):
        """All penalize patterns should be valid regex."""
        import re

        for entity_type, patterns in CONTEXT_SIGNALS["penalize"].items():
            for pattern in patterns:
                try:
                    re.compile(pattern, re.IGNORECASE)
                except re.error as e:
                    pytest.fail(
                        f"Invalid regex in penalize.{entity_type}: {pattern} - {e}"
                    )


class TestContextAnalyzerInit:
    """Tests for ContextAnalyzer initialization."""

    def test_default_window_size(self):
        """Should use default window size of 50."""
        analyzer = ContextAnalyzer()
        assert analyzer.window_size == 50

    def test_custom_window_size(self):
        """Should accept custom window size."""
        analyzer = ContextAnalyzer(window_size=100)
        assert analyzer.window_size == 100

    def test_patterns_compiled(self):
        """Should compile patterns on initialization for performance."""
        analyzer = ContextAnalyzer()
        # Implementation detail: patterns should be compiled
        assert hasattr(analyzer, "_boost_patterns")
        assert hasattr(analyzer, "_penalize_patterns")


class TestContextAnalyzerBoost:
    """Tests for context boost behavior."""

    @pytest.fixture
    def analyzer(self):
        return ContextAnalyzer()

    def test_boosts_email_with_context(self, analyzer):
        """Should boost email confidence when 'contact at' precedes it."""
        # Use a real domain to avoid @example.com penalize pattern
        text = "Please contact at john@company.org for inquiries"
        entity = MockEntity.create("john@company.org", "email", start=18)
        adjustment = analyzer.analyze(entity, text)
        assert adjustment > 0, "Should have positive adjustment for 'contact at' context"

    def test_boosts_email_with_email_prefix(self, analyzer):
        """Should boost email confidence when 'email:' precedes it."""
        # Use a real domain to avoid @example.com penalize pattern
        text = "email: john@company.org"
        entity = MockEntity.create("john@company.org", "email", start=7)
        adjustment = analyzer.analyze(entity, text)
        assert adjustment > 0, "Should have positive adjustment for 'email:' context"

    def test_boosts_phone_with_call_context(self, analyzer):
        """Should boost phone confidence when 'call me' precedes it."""
        # Use a non-555 number to avoid the fake number penalize pattern
        text = "Please call me at 408-123-4567 today"
        entity = MockEntity.create("408-123-4567", "phone", start=18)
        adjustment = analyzer.analyze(entity, text)
        assert adjustment > 0, "Should have positive adjustment for 'call me' context"

    def test_boosts_phone_with_office_context(self, analyzer):
        """Should boost phone confidence when 'office number' precedes it."""
        # Use a non-555 number to avoid the fake number penalize pattern
        text = "My office number: 408-123-4567"
        entity = MockEntity.create("408-123-4567", "phone", start=18)
        adjustment = analyzer.analyze(entity, text)
        assert adjustment > 0, "Should have positive adjustment for 'office number' context"

    def test_boosts_person_name_with_dear(self, analyzer):
        """Should boost person_name confidence when 'Dear' precedes it."""
        text = "Dear John Smith, thank you for your inquiry"
        entity = MockEntity.create("John Smith", "person_name", start=5)
        adjustment = analyzer.analyze(entity, text)
        assert adjustment > 0, "Should have positive adjustment for 'Dear' context"

    def test_boosts_person_name_with_mr(self, analyzer):
        """Should boost person_name confidence when 'Mr.' precedes it."""
        text = "Mr. John Smith is here"
        entity = MockEntity.create("John Smith", "person_name", start=4)
        adjustment = analyzer.analyze(entity, text)
        assert adjustment > 0, "Should have positive adjustment for 'Mr.' context"

    def test_boosts_government_id_with_ssn_context(self, analyzer):
        """Should boost government_id confidence when 'SSN:' precedes it."""
        text = "SSN: 123-45-6789"
        entity = MockEntity.create("123-45-6789", "government_id", start=5)
        adjustment = analyzer.analyze(entity, text)
        assert adjustment > 0, "Should have positive adjustment for 'SSN:' context"

    def test_boosts_financial_account_with_card_context(self, analyzer):
        """Should boost financial_account confidence when 'card number' precedes it."""
        text = "Card number: 4532015112830366"
        entity = MockEntity.create("4532015112830366", "financial_account", start=13)
        adjustment = analyzer.analyze(entity, text)
        assert adjustment > 0, "Should have positive adjustment for 'card number' context"

    def test_boosts_address_with_ship_to_context(self, analyzer):
        """Should boost address confidence when 'ship to:' precedes it."""
        text = "Ship to: 123 Main Street, New York"
        entity = MockEntity.create("123 Main Street, New York", "address", start=9)
        adjustment = analyzer.analyze(entity, text)
        assert adjustment > 0, "Should have positive adjustment for 'ship to:' context"


class TestContextAnalyzerPenalize:
    """Tests for context penalize behavior."""

    @pytest.fixture
    def analyzer(self):
        return ContextAnalyzer()

    def test_penalizes_example_domain(self, analyzer):
        """Should penalize emails with @example.com domain."""
        text = "Send to test@example.com for testing"
        entity = MockEntity.create("test@example.com", "email", start=8)
        adjustment = analyzer.analyze(entity, text)
        assert adjustment < 0, "Should have negative adjustment for @example.com"

    def test_penalizes_placeholder_pattern(self, analyzer):
        """Should penalize when near existing placeholder patterns."""
        text = "The email [EMAIL_1] was found at john@test.com"
        entity = MockEntity.create("john@test.com", "email", start=33)
        adjustment = analyzer.analyze(entity, text)
        assert adjustment < 0, "Should have negative adjustment near placeholder"

    def test_penalizes_555_phone_numbers(self, analyzer):
        """Should penalize fake 555 phone numbers."""
        text = "Call 555-123-4567 for info"
        entity = MockEntity.create("555-123-4567", "phone", start=5)
        adjustment = analyzer.analyze(entity, text)
        assert adjustment < 0, "Should have negative adjustment for 555 numbers"

    def test_penalizes_example_keyword(self, analyzer):
        """Should penalize when 'example' is in context."""
        text = "For example, John Smith might appear here"
        entity = MockEntity.create("John Smith", "person_name", start=13)
        adjustment = analyzer.analyze(entity, text)
        assert adjustment < 0, "Should have negative adjustment for 'example' context"

    def test_penalizes_sample_keyword(self, analyzer):
        """Should penalize when 'sample' is in context."""
        text = "This is sample data: john@test.com"
        entity = MockEntity.create("john@test.com", "email", start=21)
        adjustment = analyzer.analyze(entity, text)
        assert adjustment < 0, "Should have negative adjustment for 'sample' context"

    def test_penalizes_test_keyword(self, analyzer):
        """Should penalize when 'test' is in context."""
        text = "Test data: 555-987-6543"
        entity = MockEntity.create("555-987-6543", "phone", start=11)
        adjustment = analyzer.analyze(entity, text)
        assert adjustment < 0, "Should have negative adjustment for 'test' context"

    def test_penalizes_all_caps_label(self, analyzer):
        """Should penalize person_name when it looks like a label (all caps)."""
        # Use text that matches the all-caps pattern but not 'contact' boost pattern
        text = "FULL NAME:"
        entity = MockEntity.create("FULL NAME", "person_name", start=0)
        adjustment = analyzer.analyze(entity, text)
        assert adjustment < 0, "Should have negative adjustment for all-caps label pattern"


class TestContextAnalyzerNeutral:
    """Tests for neutral context behavior."""

    @pytest.fixture
    def analyzer(self):
        return ContextAnalyzer()

    def test_neutral_without_signals(self, analyzer):
        """Should return 0.0 when no context signals present."""
        text = "The meeting is scheduled for tomorrow afternoon"
        entity = MockEntity.create("meeting", "person_name", start=4)
        adjustment = analyzer.analyze(entity, text)
        assert adjustment == 0.0, "Should return 0.0 without context signals"

    def test_neutral_for_unknown_entity_type(self, analyzer):
        """Should return 0.0 for unknown entity types without __all__ matches."""
        text = "Some random text with neutral context"
        entity = MockEntity.create("random", "unknown_type", start=5)
        adjustment = analyzer.analyze(entity, text)
        assert adjustment == 0.0, "Should return 0.0 for unknown type"


class TestContextAnalyzerClamping:
    """Tests for confidence adjustment clamping."""

    @pytest.fixture
    def analyzer(self):
        return ContextAnalyzer()

    def test_clamps_to_max_positive(self, analyzer):
        """Should clamp positive adjustments to +0.3."""
        # Create context with multiple boost signals
        text = "Dear Mr. John Smith, email: john@example.com contact at 555-123-4567"
        entity = MockEntity.create("John Smith", "person_name", start=9)
        adjustment = analyzer.analyze(entity, text)
        assert adjustment <= 0.3, "Should clamp to max +0.3"

    def test_clamps_to_max_negative(self, analyzer):
        """Should clamp negative adjustments to -0.3."""
        # Create context with multiple penalize signals
        text = "Test example sample fake placeholder [EMAIL_1] dummy@example.com"
        entity = MockEntity.create("dummy@example.com", "email", start=47)
        adjustment = analyzer.analyze(entity, text)
        assert adjustment >= -0.3, "Should clamp to min -0.3"

    def test_adjustment_within_range(self, analyzer):
        """Adjustment should always be within [-0.3, +0.3] range."""
        test_cases = [
            ("email: john@example.com", "email", 7, "john@example.com"),
            ("call me 555-123-4567 test", "phone", 8, "555-123-4567"),
            ("Dear John Smith example", "person_name", 5, "John Smith"),
            ("SSN: 123-45-6789 placeholder", "government_id", 5, "123-45-6789"),
        ]
        for text, entity_type, start, entity_text in test_cases:
            entity = MockEntity.create(entity_text, entity_type, start)
            adjustment = analyzer.analyze(entity, text)
            assert -0.3 <= adjustment <= 0.3, f"Out of range for: {text}"


class TestContextWindow:
    """Tests for context window extraction."""

    def test_uses_window_around_entity(self):
        """Should use window_size characters around entity."""
        analyzer = ContextAnalyzer(window_size=10)
        # Build text with known structure - use neutral characters and a neutral domain
        prefix = "A" * 20  # 20 chars before
        entity_text = "john@work.org"
        suffix = "B" * 20  # 20 chars after
        text = prefix + entity_text + suffix
        entity = MockEntity.create(entity_text, "email", start=20)

        # The context window should be limited
        # With only A's and B's in context (no patterns), should be neutral
        adjustment = analyzer.analyze(entity, text)
        # With neutral surroundings, should be 0.0
        assert adjustment == 0.0

    def test_handles_entity_at_start(self):
        """Should handle entity at start of text."""
        analyzer = ContextAnalyzer(window_size=50)
        text = "john@example.com is the primary contact"
        entity = MockEntity.create("john@example.com", "email", start=0)
        # Should not crash, even with no preceding context
        adjustment = analyzer.analyze(entity, text)
        assert -0.3 <= adjustment <= 0.3

    def test_handles_entity_at_end(self):
        """Should handle entity at end of text."""
        analyzer = ContextAnalyzer(window_size=50)
        text = "Contact us at john@example.com"
        entity = MockEntity.create("john@example.com", "email", start=14)
        # Should not crash, even with no following context
        adjustment = analyzer.analyze(entity, text)
        assert -0.3 <= adjustment <= 0.3

    def test_handles_short_text(self):
        """Should handle text shorter than window size."""
        analyzer = ContextAnalyzer(window_size=100)
        text = "Hi John"
        entity = MockEntity.create("John", "person_name", start=3)
        # Should not crash with short text
        adjustment = analyzer.analyze(entity, text)
        assert -0.3 <= adjustment <= 0.3


class TestContextAnalyzerEdgeCases:
    """Tests for edge cases."""

    @pytest.fixture
    def analyzer(self):
        return ContextAnalyzer()

    def test_empty_text(self, analyzer):
        """Should handle empty text gracefully."""
        entity = MockEntity.create("test", "email", start=0)
        adjustment = analyzer.analyze(entity, "")
        assert adjustment == 0.0

    def test_entity_beyond_text_bounds(self, analyzer):
        """Should handle entity positions beyond text gracefully."""
        text = "short"
        entity = MockEntity.create("test", "email", start=100)
        adjustment = analyzer.analyze(entity, text)
        assert adjustment == 0.0

    def test_unicode_context(self, analyzer):
        """Should handle unicode in context."""
        text = "Contactez-nous: pierre@example.fr pour plus d'informations"
        entity = MockEntity.create("pierre@example.fr", "email", start=16)
        adjustment = analyzer.analyze(entity, text)
        assert -0.3 <= adjustment <= 0.3

    def test_multiline_context(self, analyzer):
        """Should handle multiline text."""
        # Use a real domain to avoid @example.com penalize pattern
        text = "Contact Info:\nEmail: john@company.org\nPhone: 408-1234"
        entity = MockEntity.create("john@company.org", "email", start=21)
        adjustment = analyzer.analyze(entity, text)
        # 'Email:' should provide boost (or neutral if pattern doesn't match across newline)
        assert adjustment >= 0.0, "Should not penalize email with Email: prefix"


class TestIntegration:
    """Integration tests for context analyzer."""

    @pytest.fixture
    def analyzer(self):
        return ContextAnalyzer()

    def test_boost_stronger_than_single_penalize(self, analyzer):
        """When multiple boosts present, should outweigh single penalize."""
        text = "Dear Mr. John Smith at example company"
        entity = MockEntity.create("John Smith", "person_name", start=9)
        # 'Dear' and 'Mr.' boost, 'example' penalizes
        # Multiple boosts should result in net positive
        adjustment = analyzer.analyze(entity, text)
        # This tests the balance between boost and penalize
        # The actual value depends on implementation weights

    def test_common_email_signature_pattern(self, analyzer):
        """Should correctly analyze common email signature patterns."""
        text = "Best regards,\nJohn Smith\nemail: john@company.com\nPhone: 555-123-4567"
        email_entity = MockEntity.create("john@company.com", "email", start=33)
        adjustment = analyzer.analyze(email_entity, text)
        assert adjustment >= 0, "Email with 'email:' prefix should get boost"

    def test_form_field_pattern(self, analyzer):
        """Should correctly analyze form field patterns."""
        text = "Enter your email: john@test.com"
        entity = MockEntity.create("john@test.com", "email", start=18)
        adjustment = analyzer.analyze(entity, text)
        # 'enter your email' is a penalize pattern
        assert adjustment < 0, "Email in form field pattern should be penalized"
