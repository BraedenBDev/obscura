"""
SQLite database manager for Obscura.

Replaces sessions.json with a proper database for:
- Session storage with mappings
- Detection logging for tuning
- User corrections for local learning
"""

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class DatabaseManager:
    """
    Manages SQLite database for Obscura.

    Tables:
    - sessions: Stores anonymization sessions
    - mappings: Stores placeholder-to-original mappings per session
    - detection_log: Logs detection events for tuning
    - user_corrections: Stores user corrections for local learning
    """

    # Schema version for migrations
    SCHEMA_VERSION = 1

    def __init__(self, db_path: str):
        """
        Initialize database manager and create tables.

        Args:
            db_path: Path to SQLite database file, or ":memory:" for in-memory DB
        """
        self.db_path = db_path
        self._memory_conn: Optional[sqlite3.Connection] = None

        # Create parent directory if needed (but not for in-memory)
        if db_path != ":memory:":
            parent_dir = Path(db_path).parent
            parent_dir.mkdir(parents=True, exist_ok=True)
        else:
            # For in-memory databases, keep a persistent connection
            # otherwise each connection creates a fresh empty database
            self._memory_conn = sqlite3.connect(":memory:")
            self._memory_conn.row_factory = sqlite3.Row
            self._memory_conn.execute("PRAGMA foreign_keys = ON")

        # Initialize schema
        self._create_tables()

    @contextmanager
    def _connection(self):
        """
        Context manager for database connections.

        Ensures proper commit/rollback and connection cleanup.
        For in-memory databases, uses the persistent connection.
        """
        if self._memory_conn is not None:
            # In-memory: use persistent connection, don't close it
            try:
                yield self._memory_conn
                self._memory_conn.commit()
            except Exception:
                self._memory_conn.rollback()
                raise
        else:
            # File-based: create new connection each time
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row  # Allow dict-like access
            conn.execute("PRAGMA foreign_keys = ON")  # Enable FK constraints
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def _create_tables(self) -> None:
        """Create all required tables and indices."""
        with self._connection() as conn:
            # Sessions table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    original_text TEXT NOT NULL,
                    anonymized_text TEXT NOT NULL,
                    original_hash TEXT,
                    entity_count INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'active'
                )
            """)

            # Mappings table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mappings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    placeholder TEXT NOT NULL,
                    original_value TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    start_pos INTEGER,
                    end_pos INTEGER,
                    confidence REAL,
                    validator_results TEXT,
                    UNIQUE(session_id, placeholder)
                )
            """)

            # Detection log for tuning
            conn.execute("""
                CREATE TABLE IF NOT EXISTS detection_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    entity_type TEXT NOT NULL,
                    detected_text TEXT NOT NULL,
                    was_valid BOOLEAN NOT NULL,
                    rejection_reason TEXT,
                    confidence_original REAL,
                    confidence_adjusted REAL
                )
            """)

            # User corrections for local learning
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_corrections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    original_text TEXT NOT NULL,
                    corrected_text TEXT,
                    original_type TEXT,
                    corrected_type TEXT,
                    context_before TEXT,
                    context_after TEXT,
                    context_hash TEXT,
                    correction_kind TEXT NOT NULL,
                    times_applied INTEGER DEFAULT 0,
                    last_applied TIMESTAMP
                )
            """)

            # Create indices for performance
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_mappings_session_id
                ON mappings(session_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_mappings_placeholder
                ON mappings(placeholder)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_status
                ON sessions(status)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_expires
                ON sessions(expires_at)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_detection_log_timestamp
                ON detection_log(timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_corrections_text
                ON user_corrections(original_text)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_corrections_context_hash
                ON user_corrections(context_hash)
            """)

    # ==================== Session Management ====================

    def create_session(
        self,
        session_id: str,
        original_text: str,
        anonymized_text: str,
        mappings: Dict[str, Dict[str, Any]],
        entities: List[Dict[str, Any]],
        ttl_hours: int = 24,
    ) -> None:
        """
        Create a new anonymization session.

        Args:
            session_id: Unique session identifier
            original_text: The original text before anonymization
            anonymized_text: Text with PII replaced by placeholders
            mappings: Dict mapping placeholders to their original values and metadata
                      Format: {"[EMAIL_1]": {"original": "...", "type": "email", ...}}
            entities: List of detected entities (for entity_count)
            ttl_hours: Hours until session expires
        """
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=ttl_hours)
        original_hash = hashlib.sha256(original_text.encode()).hexdigest()[:16]

        with self._connection() as conn:
            # Insert session
            conn.execute("""
                INSERT INTO sessions (id, created_at, expires_at, original_text,
                                     anonymized_text, original_hash, entity_count, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
            """, (
                session_id,
                now.isoformat(),
                expires_at.isoformat(),
                original_text,
                anonymized_text,
                original_hash,
                len(entities),
            ))

            # Insert mappings
            for placeholder, mapping_data in mappings.items():
                original_value = mapping_data.get("original", "")
                entity_type = mapping_data.get("type", "unknown")
                start_pos = mapping_data.get("start")
                end_pos = mapping_data.get("end")
                confidence = mapping_data.get("confidence")
                validator_results = mapping_data.get("validator_results")

                # Serialize validator_results if it's a dict (even empty)
                if isinstance(validator_results, dict):
                    validator_results = json.dumps(validator_results)

                conn.execute("""
                    INSERT INTO mappings (session_id, placeholder, original_value,
                                         entity_type, start_pos, end_pos, confidence,
                                         validator_results)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    session_id,
                    placeholder,
                    original_value,
                    entity_type,
                    start_pos,
                    end_pos,
                    confidence,
                    validator_results,
                ))

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get session info including replacement map.

        Args:
            session_id: The session ID to look up

        Returns:
            Dict with session info and replacement_map, or None if not found
        """
        with self._connection() as conn:
            # Get session
            cursor = conn.execute("""
                SELECT id, created_at, expires_at, original_text, anonymized_text,
                       original_hash, entity_count, status
                FROM sessions
                WHERE id = ?
            """, (session_id,))

            row = cursor.fetchone()
            if not row:
                return None

            session = {
                "session_id": row["id"],
                "created_at": row["created_at"],
                "expires_at": row["expires_at"],
                "original_text": row["original_text"],
                "anonymized_text": row["anonymized_text"],
                "original_hash": row["original_hash"],
                "entity_count": row["entity_count"],
                "status": row["status"],
            }

            # Get mappings
            cursor = conn.execute("""
                SELECT placeholder, original_value
                FROM mappings
                WHERE session_id = ?
            """, (session_id,))

            replacement_map = {}
            for mapping_row in cursor.fetchall():
                replacement_map[mapping_row["placeholder"]] = mapping_row["original_value"]

            session["replacement_map"] = replacement_map

            return session

    def get_session_mappings(self, session_id: str) -> Optional[Dict[str, str]]:
        """
        Get just the mappings dict for a session.

        Args:
            session_id: The session ID to look up

        Returns:
            Dict mapping placeholders to original values, or None if not found
        """
        with self._connection() as conn:
            cursor = conn.execute("""
                SELECT placeholder, original_value
                FROM mappings
                WHERE session_id = ?
            """, (session_id,))

            rows = cursor.fetchall()
            if not rows:
                # Check if session exists with no mappings
                session_cursor = conn.execute(
                    "SELECT id FROM sessions WHERE id = ?", (session_id,)
                )
                if session_cursor.fetchone():
                    return {}  # Session exists but has no mappings
                return None  # Session doesn't exist

            return {row["placeholder"]: row["original_value"] for row in rows}

    def find_mappings_for_placeholders(
        self, placeholders: List[str]
    ) -> Dict[str, str]:
        """
        Find mappings for given placeholders across all sessions.

        Args:
            placeholders: List of placeholder strings to look up

        Returns:
            Dict mapping found placeholders to their original values
        """
        if not placeholders:
            return {}

        with self._connection() as conn:
            # Build query with placeholders
            placeholders_param = ",".join("?" * len(placeholders))
            cursor = conn.execute(f"""
                SELECT DISTINCT placeholder, original_value
                FROM mappings
                WHERE placeholder IN ({placeholders_param})
            """, placeholders)

            return {row["placeholder"]: row["original_value"] for row in cursor.fetchall()}

    def mark_session_restored(self, session_id: str) -> None:
        """
        Mark a session as restored.

        Args:
            session_id: The session ID to update
        """
        with self._connection() as conn:
            conn.execute("""
                UPDATE sessions
                SET status = 'restored'
                WHERE id = ?
            """, (session_id,))

    def list_sessions(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all sessions, optionally filtered by status.

        Args:
            status: Filter by status ('active', 'restored'), or None for all

        Returns:
            List of session info dicts (without full text content)
        """
        with self._connection() as conn:
            if status:
                cursor = conn.execute("""
                    SELECT id, created_at, expires_at, entity_count, status
                    FROM sessions
                    WHERE status = ?
                    ORDER BY created_at DESC
                """, (status,))
            else:
                cursor = conn.execute("""
                    SELECT id, created_at, expires_at, entity_count, status
                    FROM sessions
                    ORDER BY created_at DESC
                """)

            return [
                {
                    "session_id": row["id"],
                    "created_at": row["created_at"],
                    "expires_at": row["expires_at"],
                    "entity_count": row["entity_count"],
                    "status": row["status"],
                }
                for row in cursor.fetchall()
            ]

    # ==================== Detection Logging ====================

    def log_detection(
        self,
        entity_type: str,
        detected_text: str,
        was_valid: bool,
        rejection_reason: Optional[str] = None,
        confidence_original: Optional[float] = None,
        confidence_adjusted: Optional[float] = None,
    ) -> None:
        """
        Log a detection event for later analysis and tuning.

        Args:
            entity_type: The type of entity detected
            detected_text: The text that was detected
            was_valid: Whether the detection was valid after validation
            rejection_reason: Reason for rejection if was_valid is False
            confidence_original: Original confidence score
            confidence_adjusted: Adjusted confidence after validation
        """
        with self._connection() as conn:
            conn.execute("""
                INSERT INTO detection_log (entity_type, detected_text, was_valid,
                                          rejection_reason, confidence_original,
                                          confidence_adjusted)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                entity_type,
                detected_text,
                was_valid,
                rejection_reason,
                confidence_original,
                confidence_adjusted,
            ))

    def get_rejection_stats(self) -> Dict[str, Dict[str, int]]:
        """
        Get rejection statistics by entity type and reason.

        Returns:
            Nested dict: {entity_type: {rejection_reason: count}}
        """
        with self._connection() as conn:
            cursor = conn.execute("""
                SELECT entity_type, rejection_reason, COUNT(*) as count
                FROM detection_log
                WHERE was_valid = 0 AND rejection_reason IS NOT NULL
                GROUP BY entity_type, rejection_reason
            """)

            stats: Dict[str, Dict[str, int]] = {}
            for row in cursor.fetchall():
                entity_type = row["entity_type"]
                reason = row["rejection_reason"]
                count = row["count"]

                if entity_type not in stats:
                    stats[entity_type] = {}
                stats[entity_type][reason] = count

            return stats

    # ==================== User Corrections ====================

    def add_correction(
        self,
        original_text: str,
        corrected_text: Optional[str],
        original_type: Optional[str],
        corrected_type: Optional[str],
        context_before: Optional[str],
        context_after: Optional[str],
        correction_kind: str,
    ) -> int:
        """
        Add a user correction for local learning.

        Args:
            original_text: The originally detected text
            corrected_text: The user's corrected text (None if deleted)
            original_type: The original entity type
            corrected_type: The user's corrected type (None if no change)
            context_before: Text before the detection
            context_after: Text after the detection
            correction_kind: Type of correction ('confirmed', 'rejected', 'reclassified')

        Returns:
            The ID of the new correction record
        """
        # Generate context hash for lookup
        context_hash = None
        if context_before or context_after:
            context_str = f"{context_before or ''}|{original_text}|{context_after or ''}"
            context_hash = hashlib.sha256(context_str.encode()).hexdigest()[:32]

        with self._connection() as conn:
            cursor = conn.execute("""
                INSERT INTO user_corrections (original_text, corrected_text,
                                             original_type, corrected_type,
                                             context_before, context_after,
                                             context_hash, correction_kind)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                original_text,
                corrected_text,
                original_type,
                corrected_type,
                context_before,
                context_after,
                context_hash,
                correction_kind,
            ))
            return cursor.lastrowid

    def find_correction_by_text(
        self,
        text: str,
        entity_type: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Find a correction by the original text (case-insensitive).

        Args:
            text: The text to look up
            entity_type: Optional entity type filter

        Returns:
            The correction dict, or None if not found
        """
        with self._connection() as conn:
            if entity_type:
                cursor = conn.execute("""
                    SELECT * FROM user_corrections
                    WHERE LOWER(original_text) = LOWER(?)
                    AND original_type = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (text, entity_type))
            else:
                cursor = conn.execute("""
                    SELECT * FROM user_corrections
                    WHERE LOWER(original_text) = LOWER(?)
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (text,))

            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def find_correction_by_context(
        self,
        original_text: str,
        context_before: Optional[str],
        context_after: Optional[str],
        entity_type: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Find a correction by context hash.

        Args:
            original_text: The original detected text
            context_before: Text before the detection
            context_after: Text after the detection
            entity_type: Optional entity type filter

        Returns:
            The correction dict, or None if not found
        """
        context_str = f"{context_before or ''}|{original_text}|{context_after or ''}"
        context_hash = hashlib.sha256(context_str.encode()).hexdigest()[:32]

        with self._connection() as conn:
            if entity_type:
                cursor = conn.execute("""
                    SELECT * FROM user_corrections
                    WHERE context_hash = ?
                    AND original_type = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (context_hash, entity_type))
            else:
                cursor = conn.execute("""
                    SELECT * FROM user_corrections
                    WHERE context_hash = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (context_hash,))

            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def get_corrections_by_kind(self, correction_kind: str) -> List[Dict[str, Any]]:
        """
        Get all corrections of a specific kind.

        Args:
            correction_kind: The kind to filter by

        Returns:
            List of correction dicts
        """
        with self._connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM user_corrections
                WHERE correction_kind = ?
                ORDER BY created_at DESC
            """, (correction_kind,))

            return [dict(row) for row in cursor.fetchall()]

    def increment_correction_applied(self, correction_id: int) -> None:
        """
        Increment the times_applied counter for a correction.

        Args:
            correction_id: The ID of the correction to update
        """
        now = datetime.now(timezone.utc).isoformat()

        with self._connection() as conn:
            conn.execute("""
                UPDATE user_corrections
                SET times_applied = times_applied + 1,
                    last_applied = ?
                WHERE id = ?
            """, (now, correction_id))

    # ==================== Cleanup Operations ====================

    def cleanup_expired(self) -> int:
        """
        Delete expired sessions and their mappings.

        Returns:
            Number of sessions deleted
        """
        now = datetime.now(timezone.utc).isoformat()

        with self._connection() as conn:
            # Count before delete
            cursor = conn.execute("""
                SELECT COUNT(*) FROM sessions
                WHERE expires_at < ?
            """, (now,))
            count = cursor.fetchone()[0]

            # Delete (cascades to mappings)
            conn.execute("""
                DELETE FROM sessions
                WHERE expires_at < ?
            """, (now,))

            return count

    def cleanup_old_logs(self, days: int = 30) -> int:
        """
        Delete detection logs older than specified days.

        Args:
            days: Delete logs older than this many days

        Returns:
            Number of logs deleted
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        with self._connection() as conn:
            # Count before delete
            cursor = conn.execute("""
                SELECT COUNT(*) FROM detection_log
                WHERE timestamp < ?
            """, (cutoff,))
            count = cursor.fetchone()[0]

            conn.execute("""
                DELETE FROM detection_log
                WHERE timestamp < ?
            """, (cutoff,))

            return count

    # ==================== Data Management ====================

    def wipe_all(self) -> Dict[str, int]:
        """
        Completely reset the database (delete all data, keep tables).

        Returns:
            Dict with counts of deleted records by table
        """
        stats = {}

        with self._connection() as conn:
            # Get counts
            for table in ["sessions", "mappings", "detection_log", "user_corrections"]:
                cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
                stats[f"{table}_deleted"] = cursor.fetchone()[0]

            # Delete all data
            conn.execute("DELETE FROM mappings")
            conn.execute("DELETE FROM sessions")
            conn.execute("DELETE FROM detection_log")
            conn.execute("DELETE FROM user_corrections")

        return stats

    def wipe_sessions_only(self) -> int:
        """
        Delete all sessions and mappings, but keep corrections and logs.

        Returns:
            Number of sessions deleted
        """
        with self._connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM sessions")
            count = cursor.fetchone()[0]

            conn.execute("DELETE FROM mappings")
            conn.execute("DELETE FROM sessions")

            return count

    def get_stats(self) -> Dict[str, Any]:
        """
        Get database statistics.

        Returns:
            Dict with counts and size info
        """
        stats = {}

        with self._connection() as conn:
            # Counts
            cursor = conn.execute("SELECT COUNT(*) FROM sessions")
            stats["session_count"] = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(*) FROM mappings")
            stats["mapping_count"] = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(*) FROM user_corrections")
            stats["correction_count"] = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(*) FROM detection_log")
            stats["detection_log_count"] = cursor.fetchone()[0]

            # Active vs restored sessions
            cursor = conn.execute("""
                SELECT status, COUNT(*) FROM sessions GROUP BY status
            """)
            stats["sessions_by_status"] = {row[0]: row[1] for row in cursor.fetchall()}

        # Database file size (not for in-memory)
        if self.db_path != ":memory:" and os.path.exists(self.db_path):
            stats["db_size_bytes"] = os.path.getsize(self.db_path)
        else:
            stats["db_size_bytes"] = 0

        return stats

    def export_to_json(self, path: str) -> None:
        """
        Export all data to JSON file.

        Args:
            path: Path to write JSON file
        """
        data = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "sessions": [],
            "mappings": [],
            "corrections": [],
            "detection_log": [],
        }

        with self._connection() as conn:
            # Export sessions
            cursor = conn.execute("SELECT * FROM sessions")
            for row in cursor.fetchall():
                data["sessions"].append(dict(row))

            # Export mappings
            cursor = conn.execute("SELECT * FROM mappings")
            for row in cursor.fetchall():
                data["mappings"].append(dict(row))

            # Export corrections
            cursor = conn.execute("SELECT * FROM user_corrections")
            for row in cursor.fetchall():
                data["corrections"].append(dict(row))

            # Export detection log
            cursor = conn.execute("SELECT * FROM detection_log")
            for row in cursor.fetchall():
                data["detection_log"].append(dict(row))

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
