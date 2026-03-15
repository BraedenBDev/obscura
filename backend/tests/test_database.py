"""
Tests for the SQLite database manager.

Run with: python -m pytest tests/test_database.py -v
"""

import os
import json
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from obscura.database import DatabaseManager


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    db = DatabaseManager(db_path)
    yield db

    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def populated_db(temp_db):
    """Database with sample data."""
    # Create a session with mappings
    temp_db.create_session(
        session_id="test-session-1",
        original_text="Contact John at john@example.com",
        anonymized_text="Contact [PERSON_NAME_1] at [EMAIL_1]",
        mappings={
            "[PERSON_NAME_1]": {
                "original": "John",
                "type": "person_name",
                "start": 8,
                "end": 12,
                "confidence": 0.95,
            },
            "[EMAIL_1]": {
                "original": "john@example.com",
                "type": "email",
                "start": 16,
                "end": 32,
                "confidence": 0.99,
            },
        },
        entities=[
            {"text": "John", "label": "person_name", "score": 0.95},
            {"text": "john@example.com", "label": "email", "score": 0.99},
        ],
        ttl_hours=24,
    )

    # Add a correction
    temp_db.add_correction(
        original_text="John Smith",
        corrected_text=None,
        original_type="person_name",
        corrected_type=None,
        context_before="Contact ",
        context_after=" at",
        correction_kind="confirmed",
    )

    return temp_db


class TestDatabaseInit:
    """Tests for database initialization."""

    def test_init_creates_tables(self, temp_db):
        """Database init should create all required tables."""
        with temp_db._connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = {row[0] for row in cursor.fetchall()}

        expected = {"sessions", "mappings", "detection_log", "user_corrections"}
        assert expected.issubset(tables), f"Missing tables: {expected - tables}"

    def test_init_creates_indices(self, temp_db):
        """Database init should create performance indices."""
        with temp_db._connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
            indices = {row[0] for row in cursor.fetchall()}

        # Should have at least session_id index on mappings
        assert any("session_id" in idx for idx in indices)

    def test_init_creates_directory_if_needed(self):
        """Should create parent directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nested_path = os.path.join(tmpdir, "subdir", "test.db")
            db = DatabaseManager(nested_path)
            assert os.path.exists(nested_path)
            os.unlink(nested_path)

    def test_init_works_with_memory_db(self):
        """Should support in-memory database for testing."""
        db = DatabaseManager(":memory:")
        assert db is not None
        # Should be able to create sessions
        db.create_session("mem-test", "text", "text", {}, [], 1)
        session = db.get_session("mem-test")
        assert session is not None


class TestSessionManagement:
    """Tests for session CRUD operations."""

    def test_create_and_get_session(self, temp_db):
        """Should create session and retrieve it correctly."""
        session_id = "test-123"
        original = "My email is test@example.com"
        anonymized = "My email is [EMAIL_1]"
        mappings = {
            "[EMAIL_1]": {
                "original": "test@example.com",
                "type": "email",
                "start": 12,
                "end": 28,
                "confidence": 0.98,
            }
        }
        entities = [{"text": "test@example.com", "label": "email", "score": 0.98}]

        temp_db.create_session(session_id, original, anonymized, mappings, entities, 24)

        session = temp_db.get_session(session_id)

        assert session is not None
        assert session["session_id"] == session_id
        assert session["original_text"] == original
        assert session["anonymized_text"] == anonymized
        assert session["entity_count"] == 1
        assert session["status"] == "active"
        assert "[EMAIL_1]" in session["replacement_map"]
        assert session["replacement_map"]["[EMAIL_1]"] == "test@example.com"

    def test_get_nonexistent_session(self, temp_db):
        """Should return None for non-existent session."""
        session = temp_db.get_session("does-not-exist")
        assert session is None

    def test_get_session_mappings(self, populated_db):
        """Should return just the mappings dict."""
        mappings = populated_db.get_session_mappings("test-session-1")

        assert mappings is not None
        assert "[PERSON_NAME_1]" in mappings
        assert "[EMAIL_1]" in mappings
        assert mappings["[EMAIL_1]"] == "john@example.com"

    def test_mark_session_restored(self, populated_db):
        """Should update session status to restored."""
        populated_db.mark_session_restored("test-session-1")

        session = populated_db.get_session("test-session-1")
        assert session["status"] == "restored"

    def test_list_sessions_all(self, populated_db):
        """Should list all sessions."""
        # Add another session
        populated_db.create_session("test-session-2", "text", "text", {}, [], 24)

        sessions = populated_db.list_sessions()
        assert len(sessions) == 2

    def test_list_sessions_by_status(self, populated_db):
        """Should filter sessions by status."""
        populated_db.mark_session_restored("test-session-1")
        populated_db.create_session("test-session-2", "text", "text", {}, [], 24)

        active_sessions = populated_db.list_sessions(status="active")
        restored_sessions = populated_db.list_sessions(status="restored")

        assert len(active_sessions) == 1
        assert len(restored_sessions) == 1
        assert restored_sessions[0]["session_id"] == "test-session-1"

    def test_session_expiration(self, temp_db):
        """Sessions should have correct expiration timestamps."""
        temp_db.create_session("exp-test", "text", "text", {}, [], ttl_hours=1)

        with temp_db._connection() as conn:
            cursor = conn.execute(
                "SELECT created_at, expires_at FROM sessions WHERE id = ?",
                ("exp-test",)
            )
            row = cursor.fetchone()

        created = datetime.fromisoformat(row[0])
        expires = datetime.fromisoformat(row[1])

        # Expiration should be ~1 hour after creation
        delta = expires - created
        assert 3500 < delta.total_seconds() < 3700  # Allow 100s tolerance


class TestMappingsLookup:
    """Tests for finding mappings across sessions."""

    def test_find_mappings_for_placeholders(self, populated_db):
        """Should find mappings for given placeholders."""
        placeholders = ["[EMAIL_1]", "[PERSON_NAME_1]"]
        result = populated_db.find_mappings_for_placeholders(placeholders)

        assert "[EMAIL_1]" in result
        assert "[PERSON_NAME_1]" in result
        assert result["[EMAIL_1]"] == "john@example.com"
        assert result["[PERSON_NAME_1]"] == "John"

    def test_find_mappings_partial(self, populated_db):
        """Should return only found mappings."""
        placeholders = ["[EMAIL_1]", "[NONEXISTENT]"]
        result = populated_db.find_mappings_for_placeholders(placeholders)

        assert "[EMAIL_1]" in result
        assert "[NONEXISTENT]" not in result

    def test_find_mappings_empty_input(self, populated_db):
        """Should handle empty placeholder list."""
        result = populated_db.find_mappings_for_placeholders([])
        assert result == {}

    def test_find_mappings_across_sessions(self, temp_db):
        """Should find mappings across multiple sessions."""
        # Create two sessions
        temp_db.create_session(
            "session-a", "orig1", "anon1",
            {"[EMAIL_1]": {"original": "a@example.com", "type": "email"}},
            [], 24
        )
        temp_db.create_session(
            "session-b", "orig2", "anon2",
            {"[PHONE_1]": {"original": "555-1234", "type": "phone"}},
            [], 24
        )

        result = temp_db.find_mappings_for_placeholders(["[EMAIL_1]", "[PHONE_1]"])

        assert result["[EMAIL_1]"] == "a@example.com"
        assert result["[PHONE_1]"] == "555-1234"


class TestDetectionLog:
    """Tests for detection logging and stats."""

    def test_log_detection(self, temp_db):
        """Should log detection events."""
        temp_db.log_detection(
            entity_type="email",
            detected_text="test@example.com",
            was_valid=True,
            rejection_reason=None,
            confidence_original=0.95,
            confidence_adjusted=0.95,
        )

        with temp_db._connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM detection_log")
            count = cursor.fetchone()[0]

        assert count == 1

    def test_log_rejected_detection(self, temp_db):
        """Should log rejection reasons."""
        temp_db.log_detection(
            entity_type="phone",
            detected_text="123",
            was_valid=False,
            rejection_reason="too_short",
            confidence_original=0.80,
            confidence_adjusted=0.40,
        )

        stats = temp_db.get_rejection_stats()
        assert stats["phone"]["too_short"] == 1

    def test_get_rejection_stats(self, temp_db):
        """Should aggregate rejection stats by type and reason."""
        # Log some detections
        temp_db.log_detection("phone", "123", False, "too_short", 0.8, 0.4)
        temp_db.log_detection("phone", "abc", False, "invalid_format", 0.7, 0.3)
        temp_db.log_detection("phone", "456", False, "too_short", 0.75, 0.35)
        temp_db.log_detection("email", "bad", False, "missing_domain", 0.6, 0.2)

        stats = temp_db.get_rejection_stats()

        assert stats["phone"]["too_short"] == 2
        assert stats["phone"]["invalid_format"] == 1
        assert stats["email"]["missing_domain"] == 1


class TestUserCorrections:
    """Tests for user correction storage and lookup."""

    def test_add_and_find_correction(self, temp_db):
        """Should add correction and find it by text."""
        temp_db.add_correction(
            original_text="John Doe",
            corrected_text=None,
            original_type="person_name",
            corrected_type=None,
            context_before="Contact ",
            context_after=" today",
            correction_kind="confirmed",
        )

        correction = temp_db.find_correction_by_text("John Doe", "person_name")

        assert correction is not None
        assert correction["original_text"] == "John Doe"
        assert correction["correction_kind"] == "confirmed"

    def test_find_correction_case_insensitive(self, temp_db):
        """Should find corrections regardless of case."""
        temp_db.add_correction(
            "JOHN DOE", None, "person_name", None, "", "", "confirmed"
        )

        correction = temp_db.find_correction_by_text("john doe", "person_name")
        assert correction is not None

    def test_find_correction_by_context(self, temp_db):
        """Should find corrections by surrounding context."""
        import hashlib

        temp_db.add_correction(
            original_text="confidential",
            corrected_text=None,
            original_type="reference_number",
            corrected_type=None,
            context_before="project ",
            context_after=" data",
            correction_kind="rejected",
        )

        # Same context should match
        correction = temp_db.find_correction_by_context(
            "confidential", "project ", " data", "reference_number"
        )

        assert correction is not None
        assert correction["original_text"] == "confidential"

    def test_find_correction_no_match(self, temp_db):
        """Should return None when no correction matches."""
        correction = temp_db.find_correction_by_text("nonexistent")
        assert correction is None

    def test_get_corrections_by_kind(self, populated_db):
        """Should filter corrections by kind."""
        # Add another correction
        populated_db.add_correction(
            "secret", "classified", "reference_number", "government_id",
            "", "", "reclassified"
        )

        confirmed = populated_db.get_corrections_by_kind("confirmed")
        reclassified = populated_db.get_corrections_by_kind("reclassified")

        assert len(confirmed) == 1
        assert len(reclassified) == 1

    def test_increment_correction_applied(self, temp_db):
        """Should increment times_applied counter."""
        temp_db.add_correction(
            "test", None, "email", None, "", "", "confirmed"
        )

        correction = temp_db.find_correction_by_text("test", "email")
        correction_id = correction["id"]

        temp_db.increment_correction_applied(correction_id)
        temp_db.increment_correction_applied(correction_id)

        correction = temp_db.find_correction_by_text("test", "email")
        assert correction["times_applied"] == 2
        assert correction["last_applied"] is not None


class TestCleanup:
    """Tests for cleanup operations."""

    def test_cleanup_expired(self, temp_db):
        """Should delete expired sessions."""
        # Create an already-expired session by manipulating DB directly
        temp_db.create_session("expired", "text", "text", {}, [], 1)

        with temp_db._connection() as conn:
            past_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
            conn.execute(
                "UPDATE sessions SET expires_at = ? WHERE id = ?",
                (past_time, "expired")
            )
            conn.commit()

        # Also create a valid session
        temp_db.create_session("valid", "text", "text", {}, [], 24)

        deleted = temp_db.cleanup_expired()

        assert deleted == 1
        assert temp_db.get_session("expired") is None
        assert temp_db.get_session("valid") is not None

    def test_cleanup_old_logs(self, temp_db):
        """Should delete old detection logs."""
        temp_db.log_detection("email", "test", True, None, 0.9, 0.9)

        # Manipulate timestamp to be old
        with temp_db._connection() as conn:
            old_time = (datetime.now(timezone.utc) - timedelta(days=35)).isoformat()
            conn.execute("UPDATE detection_log SET timestamp = ?", (old_time,))
            conn.commit()

        deleted = temp_db.cleanup_old_logs(days=30)

        assert deleted == 1


class TestWipe:
    """Tests for data wiping operations."""

    def test_wipe_all(self, populated_db):
        """Should completely reset database."""
        # Verify data exists
        assert populated_db.get_session("test-session-1") is not None

        stats = populated_db.wipe_all()

        assert stats["sessions_deleted"] >= 1
        assert populated_db.get_session("test-session-1") is None

        # Tables should still exist
        with populated_db._connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = cursor.fetchall()
        assert len(tables) > 0

    def test_wipe_sessions_only(self, populated_db):
        """Should only wipe sessions and mappings, keep corrections."""
        corrections_before = populated_db.get_corrections_by_kind("confirmed")

        populated_db.wipe_sessions_only()

        assert populated_db.get_session("test-session-1") is None

        # Corrections should remain
        corrections_after = populated_db.get_corrections_by_kind("confirmed")
        assert len(corrections_after) == len(corrections_before)


class TestStats:
    """Tests for statistics and export."""

    def test_get_stats(self, populated_db):
        """Should return database statistics."""
        stats = populated_db.get_stats()

        assert "session_count" in stats
        assert "mapping_count" in stats
        assert "correction_count" in stats
        assert "detection_log_count" in stats
        assert "db_size_bytes" in stats

        assert stats["session_count"] >= 1
        assert stats["mapping_count"] >= 2  # We have 2 mappings in populated_db
        assert stats["correction_count"] >= 1

    def test_export_to_json(self, populated_db):
        """Should export all data to JSON."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            export_path = f.name

        try:
            populated_db.export_to_json(export_path)

            with open(export_path, "r") as f:
                data = json.load(f)

            assert "sessions" in data
            assert "mappings" in data
            assert "corrections" in data
            assert "exported_at" in data

            assert len(data["sessions"]) >= 1
            assert len(data["mappings"]) >= 2
        finally:
            os.unlink(export_path)


class TestConcurrency:
    """Tests for concurrent access handling."""

    def test_multiple_connections(self, temp_db):
        """Should handle multiple sequential connections."""
        for i in range(10):
            temp_db.create_session(f"session-{i}", "text", "text", {}, [], 24)

        sessions = temp_db.list_sessions()
        assert len(sessions) == 10

    def test_connection_context_manager(self, temp_db):
        """Connection should properly commit and close."""
        with temp_db._connection() as conn:
            conn.execute(
                "INSERT INTO detection_log (entity_type, detected_text, was_valid) "
                "VALUES (?, ?, ?)",
                ("test", "test", True)
            )

        # Should be committed and readable
        with temp_db._connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM detection_log")
            assert cursor.fetchone()[0] == 1


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_unicode_in_text(self, temp_db):
        """Should handle Unicode text correctly."""
        original = "Contact support at"
        anonymized = "Contact support at [EMAIL_1]"

        temp_db.create_session(
            "unicode-test", original, anonymized,
            {"[EMAIL_1]": {"original": "test@example.com", "type": "email"}},
            [], 24
        )

        session = temp_db.get_session("unicode-test")
        assert session["original_text"] == original

    def test_special_chars_in_mappings(self, temp_db):
        """Should handle special characters in mapping values."""
        mapping = {
            "[ADDRESS_1]": {
                "original": "123 O'Brien's Way, Apt #5",
                "type": "address"
            }
        }

        temp_db.create_session("special-chars", "text", "text", mapping, [], 24)

        result = temp_db.find_mappings_for_placeholders(["[ADDRESS_1]"])
        assert result["[ADDRESS_1]"] == "123 O'Brien's Way, Apt #5"

    def test_empty_mappings(self, temp_db):
        """Should handle sessions with no mappings."""
        temp_db.create_session("empty-mappings", "no pii here", "no pii here", {}, [], 24)

        session = temp_db.get_session("empty-mappings")
        assert session is not None
        assert session["replacement_map"] == {}
        assert session["entity_count"] == 0

    def test_large_text(self, temp_db):
        """Should handle large text content."""
        large_text = "x" * 100000
        temp_db.create_session("large-text", large_text, large_text, {}, [], 24)

        session = temp_db.get_session("large-text")
        assert len(session["original_text"]) == 100000

    def test_null_correction_fields(self, temp_db):
        """Should handle null optional fields in corrections."""
        temp_db.add_correction(
            original_text="test",
            corrected_text=None,
            original_type="email",
            corrected_type=None,
            context_before=None,
            context_after=None,
            correction_kind="rejected",
        )

        correction = temp_db.find_correction_by_text("test", "email")
        assert correction is not None
        assert correction["corrected_text"] is None
