"""
User correction layer for local learning.

Applies user feedback to improve PII detection over time:
- Rejections: Remove false positives
- Relabels: Change entity types
- Boundary fixes: Expand/contract entity boundaries
- Missed PII: Find patterns GLiNER missed

All corrections are stored locally - no cloud required.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from obscura.database import DatabaseManager
from obscura.entity_types import LABEL_TO_TYPE


@dataclass
class CorrectedEntity:
    """
    An entity that has been corrected or added by user feedback.

    Attributes:
        text: The detected/corrected text
        type: The entity type (email, phone, government_id, etc.)
        start: Start position in the original text
        end: End position in the original text
        confidence: Confidence score (1.0 for user corrections)
        source: Origin of this entity (default: "user_correction")
    """

    text: str
    type: str
    start: int
    end: int
    confidence: float
    source: str = "user_correction"


def _normalize_entity_type(label: str) -> str:
    """
    Convert GLiNER description label to short type name.

    GLiNER uses natural language descriptions like "email address",
    but our validators and placeholders use short types like "email".

    Args:
        label: GLiNER's entity label (description or short type)

    Returns:
        Short type name (e.g., "email", "phone", "person_name")
    """
    # If it's already a short type, return as-is
    if label in LABEL_TO_TYPE.values():
        return label
    # Otherwise, look up in the mapping
    return LABEL_TO_TYPE.get(label, label)


class CorrectionLayer:
    """
    Applies user corrections to GLiNER detection output.

    This layer sits between GLiNER detection and final output,
    modifying results based on accumulated user feedback:

    1. Rejections: Remove entities the user marked as false positives
    2. Relabels: Change entity types based on user corrections
    3. Boundary fixes: Expand/contract entities to correct boundaries
    4. Missed PII: Add entities GLiNER missed but user identified

    All corrections are persisted locally for future use.
    """

    def __init__(self, db: DatabaseManager):
        """
        Initialize the correction layer.

        Args:
            db: Database manager for storing/retrieving corrections
        """
        self.db = db

    def apply_corrections(
        self, entities: List[Any], full_text: str
    ) -> List[CorrectedEntity]:
        """
        Apply user corrections to GLiNER output.

        Processing order:
        1. For each entity, check for matching correction
        2. Apply rejection (remove), relabel (change type), or boundary fix
        3. Find missed PII from user's add_missed corrections
        4. Return modified entity list

        Args:
            entities: List of entities from GLiNER with .text, .label, .start, .end, .score
            full_text: The complete text being processed

        Returns:
            List of CorrectedEntity objects after applying corrections
        """
        if not full_text:
            return []

        result: List[CorrectedEntity] = []
        already_found_positions: set = set()

        # Process each entity
        for entity in entities:
            # Handle both dict (GLiNER) and object formats
            if isinstance(entity, dict):
                entity_text = entity.get("text", "")
                raw_label = entity.get("label", "")
                entity_start = entity.get("start", 0)
                entity_end = entity.get("end", 0)
                entity_score = entity.get("score", 0.0)
            else:
                entity_text = getattr(entity, "text", "")
                raw_label = getattr(entity, "label", "")
                entity_start = getattr(entity, "start", 0)
                entity_end = getattr(entity, "end", 0)
                entity_score = getattr(entity, "score", 0.0)
            entity_type = _normalize_entity_type(raw_label)  # Convert description to short type

            # Verify entity is actually in the text at expected position
            if entity_start >= len(full_text) or entity_end > len(full_text):
                continue

            # Extract context for matching
            context_before = full_text[max(0, entity_start - 20) : entity_start]
            context_after = full_text[entity_end : min(len(full_text), entity_end + 20)]

            # Find matching correction
            correction = self._find_matching_correction(
                entity_text, entity_type, context_before, context_after
            )

            if correction:
                kind = correction.get("correction_kind")

                if kind == "reject":
                    # User says this is not PII - skip it
                    self._track_correction_applied(correction)
                    continue

                elif kind == "relabel":
                    # User says this is a different type
                    corrected_type = correction.get("corrected_type", entity_type)
                    self._track_correction_applied(correction)
                    result.append(
                        CorrectedEntity(
                            text=entity_text,
                            type=corrected_type,
                            start=entity_start,
                            end=entity_end,
                            confidence=1.0,  # User-corrected = high confidence
                            source="user_correction",
                        )
                    )
                    already_found_positions.add((entity_start, entity_end))

                elif kind == "boundary":
                    # User says boundaries are wrong
                    corrected_entity = self._apply_boundary_correction(
                        entity_text,
                        entity_type,
                        entity_start,
                        entity_end,
                        correction,
                        full_text,
                    )
                    if corrected_entity:
                        self._track_correction_applied(correction)
                        result.append(corrected_entity)
                        already_found_positions.add(
                            (corrected_entity.start, corrected_entity.end)
                        )
                    else:
                        # Boundary fix failed, pass through unchanged
                        result.append(
                            CorrectedEntity(
                                text=entity_text,
                                type=entity_type,
                                start=entity_start,
                                end=entity_end,
                                confidence=entity_score,
                                source="gliner",
                            )
                        )
                        already_found_positions.add((entity_start, entity_end))

                else:
                    # Unknown correction kind, pass through
                    result.append(
                        CorrectedEntity(
                            text=entity_text,
                            type=entity_type,
                            start=entity_start,
                            end=entity_end,
                            confidence=entity_score,
                            source="gliner",
                        )
                    )
                    already_found_positions.add((entity_start, entity_end))

            else:
                # No correction found, pass through unchanged
                result.append(
                    CorrectedEntity(
                        text=entity_text,
                        type=entity_type,
                        start=entity_start,
                        end=entity_end,
                        confidence=entity_score,
                        source="gliner",
                    )
                )
                already_found_positions.add((entity_start, entity_end))

        # Find missed PII from user corrections
        missed = self._find_missed_pii(full_text, already_found_positions)
        result.extend(missed)

        return result

    def _find_matching_correction(
        self,
        text: str,
        entity_type: str,
        context_before: str,
        context_after: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Find a correction that matches the given entity.

        Tries exact text match first, then context-aware match.

        Args:
            text: The detected entity text
            entity_type: The detected entity type
            context_before: Text before the entity
            context_after: Text after the entity

        Returns:
            Matching correction dict, or None if not found
        """
        # First try context-aware match (more specific)
        correction = self.db.find_correction_by_context(
            original_text=text,
            context_before=context_before,
            context_after=context_after,
            entity_type=entity_type,
        )

        if correction:
            return correction

        # Fall back to text-only match
        return self.db.find_correction_by_text(text, entity_type)

    def _find_missed_pii(
        self, full_text: str, already_found: set
    ) -> List[CorrectedEntity]:
        """
        Find text patterns that user marked as PII but GLiNER missed.

        Args:
            full_text: The complete text to search
            already_found: Set of (start, end) tuples already detected

        Returns:
            List of CorrectedEntity for missed PII
        """
        missed: List[CorrectedEntity] = []

        # Get all add_missed corrections
        corrections = self.db.get_corrections_by_kind("add_missed")

        for correction in corrections:
            search_text = correction.get("original_text", "")
            entity_type = correction.get("corrected_type", "")

            if not search_text or not entity_type:
                continue

            # Find all occurrences in full_text
            # Use case-insensitive search
            pattern = re.escape(search_text)
            for match in re.finditer(pattern, full_text, re.IGNORECASE):
                start = match.start()
                end = match.end()

                # Check if this position overlaps with already found entities
                is_duplicate = any(
                    self._positions_overlap(start, end, found_start, found_end)
                    for found_start, found_end in already_found
                )

                if not is_duplicate:
                    # Track that we used this correction
                    self._track_correction_applied(correction)

                    missed.append(
                        CorrectedEntity(
                            text=match.group(),  # Use actual matched text (preserves case)
                            type=entity_type,
                            start=start,
                            end=end,
                            confidence=1.0,
                            source="user_correction",
                        )
                    )

        return missed

    def _positions_overlap(
        self, start1: int, end1: int, start2: int, end2: int
    ) -> bool:
        """Check if two position ranges overlap."""
        return start1 < end2 and start2 < end1

    def _apply_boundary_correction(
        self,
        original_text: str,
        entity_type: str,
        original_start: int,
        original_end: int,
        correction: Dict[str, Any],
        full_text: str,
    ) -> Optional[CorrectedEntity]:
        """
        Expand or contract entity boundaries based on user correction.

        Args:
            original_text: The originally detected text
            entity_type: The entity type
            original_start: Original start position
            original_end: Original end position
            correction: The correction dict with corrected_text
            full_text: The complete text

        Returns:
            CorrectedEntity with updated boundaries, or None if correction can't be applied
        """
        corrected_text = correction.get("corrected_text", "")

        if not corrected_text:
            return None

        # Try to find the corrected text in the vicinity of the original
        # Search in a window around the original position
        search_start = max(0, original_start - 50)
        search_end = min(len(full_text), original_end + 50)
        search_window = full_text[search_start:search_end]

        # Find the corrected text in the window
        idx = search_window.find(corrected_text)

        if idx == -1:
            # Try case-insensitive
            idx = search_window.lower().find(corrected_text.lower())
            if idx != -1:
                # Use actual case from text
                corrected_text = search_window[idx : idx + len(corrected_text)]

        if idx == -1:
            return None

        # Calculate new positions
        new_start = search_start + idx
        new_end = new_start + len(corrected_text)

        return CorrectedEntity(
            text=corrected_text,
            type=entity_type,
            start=new_start,
            end=new_end,
            confidence=1.0,
            source="user_correction",
        )

    def _track_correction_applied(self, correction: Dict[str, Any]) -> None:
        """
        Increment the times_applied counter for a correction.

        Args:
            correction: The correction dict with 'id' field
        """
        correction_id = correction.get("id")
        if correction_id:
            self.db.increment_correction_applied(correction_id)

    # ==================== User-facing methods ====================

    def add_rejection(
        self,
        text: str,
        detected_type: str,
        context_before: str,
        context_after: str,
    ) -> int:
        """
        Record that user says this is NOT PII.

        Use when GLiNER incorrectly detected something as PII.
        Example: "Email" (the word) detected as person_name.

        Args:
            text: The text that was incorrectly detected
            detected_type: The type GLiNER assigned
            context_before: Text before the detection
            context_after: Text after the detection

        Returns:
            The correction ID
        """
        return self.db.add_correction(
            original_text=text,
            corrected_text=None,
            original_type=detected_type,
            corrected_type=None,
            context_before=context_before,
            context_after=context_after,
            correction_kind="reject",
        )

    def add_relabel(
        self,
        text: str,
        original_type: str,
        corrected_type: str,
        context_before: str,
        context_after: str,
    ) -> int:
        """
        Record that user says this is actually a different type of PII.

        Use when GLiNER detected PII but assigned wrong type.
        Example: "123-45-6789" detected as phone but is actually SSN.

        Args:
            text: The detected text
            original_type: The type GLiNER assigned
            corrected_type: The correct type per user
            context_before: Text before the detection
            context_after: Text after the detection

        Returns:
            The correction ID
        """
        return self.db.add_correction(
            original_text=text,
            corrected_text=None,
            original_type=original_type,
            corrected_type=corrected_type,
            context_before=context_before,
            context_after=context_after,
            correction_kind="relabel",
        )

    def add_boundary_fix(
        self,
        original_text: str,
        corrected_text: str,
        entity_type: str,
        context_before: str,
        context_after: str,
    ) -> int:
        """
        Record that user says the entity boundaries were wrong.

        Use when GLiNER only captured part of the PII.
        Example: "123 Main" should be "123 Main St, New York".

        Args:
            original_text: The text GLiNER detected
            corrected_text: The full/correct text per user
            entity_type: The entity type
            context_before: Text before the detection
            context_after: Text after the detection

        Returns:
            The correction ID
        """
        return self.db.add_correction(
            original_text=original_text,
            corrected_text=corrected_text,
            original_type=entity_type,
            corrected_type=entity_type,
            context_before=context_before,
            context_after=context_after,
            correction_kind="boundary",
        )

    def add_missed_pii(
        self,
        text: str,
        entity_type: str,
        context_before: str,
        context_after: str,
    ) -> int:
        """
        Record that user says GLiNER missed this PII.

        Use when GLiNER failed to detect PII that should have been found.
        The correction layer will search for this text in future documents.

        Args:
            text: The PII text that was missed
            entity_type: The type of PII
            context_before: Text before the missed PII
            context_after: Text after the missed PII

        Returns:
            The correction ID
        """
        return self.db.add_correction(
            original_text=text,
            corrected_text=None,
            original_type=None,
            corrected_type=entity_type,
            context_before=context_before,
            context_after=context_after,
            correction_kind="add_missed",
        )
