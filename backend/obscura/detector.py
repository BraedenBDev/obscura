"""
Main PIIDetector class - integrates all pipeline components.

Pipeline flow:
1. GLiNER extraction (or mock entities for testing)
2. Validation (filter false positives)
3. User corrections (apply local learning)
4. Context analysis (adjust confidence)
5. Deduplication and threshold filtering
6. Anonymization/Restoration with session management
"""

import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from obscura.context import ContextAnalyzer
from obscura.corrections import CorrectionLayer
from obscura.database import DatabaseManager
from obscura.entity_types import ENTITY_LABELS, LABEL_TO_TYPE
from obscura.validators import ValidatorRegistry


# Pattern to detect existing Obscura placeholders (to avoid re-detection)
PLACEHOLDER_PATTERN = re.compile(r'\[([A-Z_]+)_(\d+)\]')

# Regex patterns for high-confidence PII detection (fallback for GLiNER)
REGEX_PATTERNS = {
    # Email
    "email": {
        "pattern": re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'),
        "confidence": 0.95,
        "type": "email",
    },
    # US SSN
    "ssn": {
        "pattern": re.compile(r'\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b'),
        "confidence": 0.85,
        "type": "government_id",
    },
    # US Phone (use [ ] instead of \s to avoid matching newlines)
    "phone_us": {
        "pattern": re.compile(r'\b(?:\+?1[-.  ]?)?\(?\d{3}\)?[-. ]?\d{3}[-. ]?\d{4}\b'),
        "confidence": 0.80,
        "type": "phone",
    },
    # International phone (covers +34, +44, +971, etc.) - use [ ] not \s
    "phone_intl": {
        "pattern": re.compile(r'\+\d{1,3}[-. ]?\d{1,4}[-. ]?\d{2,4}[-. ]?\d{2,4}[-. ]?\d{0,4}\b'),
        "confidence": 0.85,
        "type": "phone",
    },
    # Credit card (16 digits)
    "credit_card": {
        "pattern": re.compile(r'\b(?:\d{4}[-.\s]?){3}\d{4}\b'),
        "confidence": 0.90,
        "type": "financial_account",
    },
    # IBAN (International Bank Account Number)
    "iban": {
        "pattern": re.compile(r'\b[A-Z]{2}\d{2}[-.\s]?(?:\d{4}[-.\s]?){2,6}\d{1,4}\b'),
        "confidence": 0.95,
        "type": "iban",
    },
    # SWIFT/BIC code
    "swift_bic": {
        "pattern": re.compile(r'\b[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b'),
        "confidence": 0.85,
        "type": "bank_account",
    },
    # UK National Insurance Number
    "uk_nino": {
        "pattern": re.compile(r'\b[A-Z]{2}[-.\s]?\d{2}[-.\s]?\d{2}[-.\s]?\d{2}[-.\s]?[A-Z]\b', re.IGNORECASE),
        "confidence": 0.90,
        "type": "national_id",
    },
    # Spanish NIE (Foreigner ID)
    "spanish_nie": {
        "pattern": re.compile(r'\b[XYZ]\d{7}[A-Z]\b', re.IGNORECASE),
        "confidence": 0.90,
        "type": "national_id",
    },
    # Passport number (6-9 alphanumeric, commonly all digits)
    "passport": {
        "pattern": re.compile(r'\b\d{9}\b'),
        "confidence": 0.70,
        "type": "passport",
    },
    # Date of birth (various formats)
    "dob_dmy": {
        "pattern": re.compile(r'\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b'),
        "confidence": 0.75,
        "type": "date_of_birth",
    },
    # Employee ID pattern
    "employee_id": {
        "pattern": re.compile(r'\bEMP[-.]?\d{5,8}\b', re.IGNORECASE),
        "confidence": 0.85,
        "type": "reference_number",
    },
    # Names in email greetings (Hi John, Dear Sarah, Hello Mike, Hey Jane)
    # This catches names that GLiNER might miss in long texts
    "greeting_name": {
        "pattern": re.compile(r'\b(?:Hi|Hello|Dear|Hey|Good morning|Good afternoon|Good evening)[,\s]+([A-Z][a-z]{2,15})(?:[,\s]|$)', re.MULTILINE),
        "confidence": 0.75,
        "type": "person_name",
        "group": 1,  # Capture group 1 is the name
    },
    # European postal code + city - VERY specific to avoid false positives
    # Only matches when on its own line or after common address keywords
    # Uses lookbehind to avoid including the newline in the match
    "european_postal_city": {
        "pattern": re.compile(
            r'(?<=^|(?<=\n)|(?<=, ))'  # Lookbehind: start of line, after newline, or after ", "
            r'(\d{5}[ ]+[A-Z][a-zA-Zà-ÿÀ-ß]{2,20})'  # Capture: postal code + city
            r'(?=[ ]*$|[ ]*\n|[ ]*,)',  # Lookahead: end of line, newline, or comma
            re.MULTILINE
        ),
        "confidence": 0.70,
        "type": "address",
        "group": 1,
    },
    # Street address patterns (common international formats)
    # Matches: "Carrer de Mallorca 271", "123 Main Street", "Via Roma 45", etc.
    "street_address": {
        "pattern": re.compile(
            r'\b(?:'
            r'(?:Carrer|Calle|Via|Rue|Strasse|Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Place|Pl|Way)[ ]+(?:de[ ]+|del[ ]+|della[ ]+)?[A-Za-zà-ÿÀ-ß]+(?:[ ]+[A-Za-zà-ÿÀ-ß]+)*[ ]*,?[ ]*\d{1,5}[A-Za-z]?'
            r'|'
            r'\d{1,5}[ ]+(?:[A-Z][a-zA-Zà-ÿÀ-ß]+[ ]+)?(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Place|Pl|Way|Court|Ct)'
            r')\b',
            re.IGNORECASE
        ),
        "confidence": 0.75,
        "type": "address",
    },
}


class _EntityWrapper:
    """Lightweight wrapper for passing entity info to context analyzer."""

    __slots__ = ("start", "end", "type")

    def __init__(self, start: int, end: int, entity_type: str):
        self.start = start
        self.end = end
        self.type = entity_type


@dataclass
class Entity:
    """
    A detected PII entity.

    Attributes:
        text: The detected text
        type: Entity type (email, phone, person_name, etc.)
        start: Start position in the original text
        end: End position in the original text
        confidence: Confidence score (0.0 to 1.0)
        source: Origin of detection ("gliner", "user_correction")
        validator_results: Results from validators (for debugging)
    """

    text: str
    type: str
    start: int
    end: int
    confidence: float
    source: str = "gliner"
    validator_results: Dict = field(default_factory=dict)


@dataclass
class AnonymizeResult:
    """
    Result from anonymization.

    Attributes:
        session_id: Unique ID for this anonymization session
        anonymized_text: Text with PII replaced by placeholders
        mappings: Dict mapping placeholders to original values
        entity_count: Number of entities anonymized
        entities: List of detected entities
    """

    session_id: str
    anonymized_text: str
    mappings: Dict[str, str]
    entity_count: int
    entities: List[Entity]


@dataclass
class RestoreResult:
    """
    Result from restoration.

    Attributes:
        restored_text: Text with placeholders replaced by original values
        mappings_applied: Number of mappings that were applied
        session_id: The session ID if one was provided
    """

    restored_text: str
    mappings_applied: int
    session_id: Optional[str] = None


class PIIDetector:
    """
    Main PII detection and anonymization class.

    Integrates all pipeline components:
    - GLiNER model for entity extraction
    - ValidatorRegistry for filtering false positives
    - CorrectionLayer for applying user feedback
    - ContextAnalyzer for confidence adjustment
    - DatabaseManager for session persistence

    Usage:
        detector = PIIDetector()
        result = detector.anonymize("My email is john@example.com")
        # result.anonymized_text = "My email is [EMAIL_1]"
        # result.session_id can be used for restoration

        restored = detector.restore(llm_output, result.session_id)
        # restored.restored_text has original values back
    """

    # Placeholder pattern for restoration
    PLACEHOLDER_PATTERN = re.compile(r"\[([A-Z][A-Z0-9_]*?)_(\d+)\]")

    def __init__(
        self,
        db_path: str = "obscura.db",
        load_model: bool = True,
        model_name: str = "urchade/gliner_multi_pii-v1",  # PII-specific model
    ):
        """
        Initialize the PIIDetector.

        Args:
            db_path: Path to SQLite database file, or ":memory:" for testing
            load_model: Whether to load the GLiNER model (False for testing)
            model_name: Name of the GLiNER model to load
        """
        self.db = DatabaseManager(db_path)
        self.validators = ValidatorRegistry()
        self.context_analyzer = ContextAnalyzer()
        self.corrections = CorrectionLayer(self.db)

        self.model = None
        self.is_loaded = False
        self._mock_entities: Optional[List[Any]] = None  # For testing without GLiNER

        if load_model:
            self.load_model(model_name)

    def load_model(self, model_name: str = "urchade/gliner_multi_pii-v1") -> None:
        """
        Load the GLiNER model.

        Args:
            model_name: HuggingFace model name or path
        """
        try:
            from gliner import GLiNER

            # Detect device
            device = self._detect_device()
            print(f"[PIIDetector] Using device: {device}")

            # Load model
            self.model = GLiNER.from_pretrained(model_name)
            if device != "cpu":
                self.model = self.model.to(device)
                # Verify device move was successful
                try:
                    import torch
                    actual_device = next(self.model.parameters()).device.type
                    if actual_device != device:
                        print(f"[PIIDetector] Warning: Model on {actual_device}, expected {device}")
                    else:
                        print(f"[PIIDetector] Model successfully loaded on {device}")
                except Exception:
                    pass  # Non-critical, just skip verification
            else:
                print("[PIIDetector] Model loaded on CPU")

            self.is_loaded = True

        except ImportError:
            # GLiNER not installed
            self.model = None
            self.is_loaded = False
        except Exception as e:
            # Model loading failed
            self.model = None
            self.is_loaded = False

    def _detect_device(self) -> str:
        """
        Detect the best available device for inference.

        Returns:
            "cuda", "mps", or "cpu"
        """
        try:
            import torch

            if torch.cuda.is_available():
                return "cuda"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
        except ImportError:
            pass

        return "cpu"

    def detect(self, text: str, threshold: float = 0.25) -> List[Entity]:
        """
        Detect PII entities in text.

        Pipeline:
        1. Extract entities using GLiNER (or mock entities for testing)
        2. Validate each entity (filter false positives)
        3. Apply user corrections
        4. Adjust confidence based on context
        5. Filter by threshold and deduplicate

        Args:
            text: Text to analyze
            threshold: Minimum confidence score (after adjustments)

        Returns:
            List of Entity objects, sorted by start position
        """
        if not text:
            return []

        # Step 1: Extract entities
        raw_entities = self._extract_entities(text)

        if not raw_entities:
            return []

        # Step 2: Validate and filter
        validated_entities = self._validate_entities(raw_entities, text)

        # Step 3: Apply user corrections
        corrected_entities = self.corrections.apply_corrections(validated_entities, text)

        # Step 4: Context analysis (adjust confidence)
        final_entities = []
        for entity in corrected_entities:
            wrapper = _EntityWrapper(entity.start, entity.end, entity.type)
            adjustment = self.context_analyzer.analyze(wrapper, text)
            adjusted_confidence = min(1.0, max(0.0, entity.confidence + adjustment))

            final_entities.append(
                Entity(
                    text=entity.text,
                    type=entity.type,
                    start=entity.start,
                    end=entity.end,
                    confidence=adjusted_confidence,
                    source=entity.source,
                    validator_results={},
                )
            )

        # Step 5: Filter by threshold
        filtered = [e for e in final_entities if e.confidence >= threshold]

        # Step 6: Deduplicate overlapping entities (keep highest confidence)
        deduped = self._deduplicate_entities(filtered)

        # Sort by start position
        deduped.sort(key=lambda e: e.start)

        return deduped

    def _extract_entities(self, text: str, threshold: float = 0.1) -> List[Any]:
        """
        Extract entities using GLiNER and regex patterns.

        Args:
            text: Text to analyze
            threshold: Minimum score for entity extraction (GLiNER's internal threshold)

        Returns:
            List of entity objects with text, label, start, end, score
        """
        entities = []

        # Use mock entities if set (for testing)
        if self._mock_entities is not None:
            return list(self._mock_entities)

        # Use GLiNER model if loaded
        if self.model is not None and self.is_loaded:
            try:
                # Pass a low threshold to GLiNER - we filter by confidence later
                gliner_entities = self.model.predict_entities(text, ENTITY_LABELS, threshold=threshold)
                entities.extend(gliner_entities)
            except Exception:
                pass

        # Add regex-based detection for high-confidence patterns
        regex_entities = self._extract_regex_entities(text)

        # Merge: regex takes precedence for overlapping entities (higher confidence)
        for regex_ent in regex_entities:
            # Find and remove any overlapping GLiNER entities
            entities = [
                e for e in entities
                if not self._entities_overlap(regex_ent, e)
            ]
            entities.append(regex_ent)

        # Filter out any entities that are Obscura placeholders (already anonymized)
        entities = self._filter_placeholders(entities)

        return entities

    def _filter_placeholders(self, entities: List[Any]) -> List[Any]:
        """
        Filter out entities that are actually Obscura placeholders.

        This prevents re-detection of already-anonymized text like [EMAIL_1].
        """
        filtered = []
        for entity in entities:
            # Get entity text
            if isinstance(entity, dict):
                entity_text = entity.get("text", "")
            else:
                entity_text = getattr(entity, "text", "")

            # Skip if the entity text matches our placeholder pattern
            if PLACEHOLDER_PATTERN.fullmatch(entity_text):
                continue

            filtered.append(entity)

        return filtered

    def _entities_overlap(self, e1: Dict[str, Any], e2: Any) -> bool:
        """Check if two entities overlap in position."""
        if isinstance(e2, dict):
            e2_start, e2_end = e2.get("start", 0), e2.get("end", 0)
        else:
            e2_start, e2_end = getattr(e2, "start", 0), getattr(e2, "end", 0)
        return e1["start"] < e2_end and e1["end"] > e2_start

    def _extract_regex_entities(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract entities using regex patterns for high-confidence PII.

        Args:
            text: Text to analyze

        Returns:
            List of entity dicts with text, label, start, end, score
        """
        entities = []

        for pattern_name, pattern_info in REGEX_PATTERNS.items():
            pattern = pattern_info["pattern"]
            entity_type = pattern_info["type"]
            confidence = pattern_info["confidence"]
            # Some patterns use capture groups (group: 1 means use group 1)
            group_num = pattern_info.get("group", 0)

            for match in pattern.finditer(text):
                # Use capture group if specified, otherwise use full match
                try:
                    matched_text = match.group(group_num)
                    start_pos = match.start(group_num)
                    end_pos = match.end(group_num)
                except IndexError:
                    # Fallback to full match if group doesn't exist
                    matched_text = match.group()
                    start_pos = match.start()
                    end_pos = match.end()

                # Skip empty matches
                if not matched_text or not matched_text.strip():
                    continue

                entities.append({
                    "text": matched_text,
                    "label": entity_type,  # Already short type
                    "start": start_pos,
                    "end": end_pos,
                    "score": confidence,
                    "source": "regex",
                })

        return entities

    def _validate_entities(self, entities: List[Any], full_text: str) -> List[Any]:
        """
        Validate entities and filter out false positives.

        Args:
            entities: Raw entities from GLiNER
            full_text: The complete text for context

        Returns:
            Filtered list of valid entities
        """
        valid = []

        for entity in entities:
            # Handle both dict (GLiNER) and object formats
            if isinstance(entity, dict):
                entity_text = entity.get("text", "")
                raw_label = entity.get("label", "")
                entity_start = entity.get("start", 0)
                entity_end = entity.get("end", 0)
            else:
                entity_text = getattr(entity, "text", "")
                raw_label = getattr(entity, "label", "")
                entity_start = getattr(entity, "start", 0)
                entity_end = getattr(entity, "end", 0)
            # Convert GLiNER's description label to short type for validators
            entity_type = LABEL_TO_TYPE.get(raw_label, raw_label)

            # Extract context for validation
            context_start = max(0, entity_start - 50)
            context_end = min(len(full_text), entity_end + 50)
            context = full_text[context_start:context_end]

            # Run validation
            result = self.validators.validate(entity_text, entity_type, context)

            if result.is_valid:
                valid.append(entity)
            else:
                # Log rejection
                entity_score = entity.get("score") if isinstance(entity, dict) else getattr(entity, "score", None)
                self.db.log_detection(
                    entity_type=entity_type,
                    detected_text=entity_text,
                    was_valid=False,
                    rejection_reason=result.rejection_reason,
                    confidence_original=entity_score,
                    confidence_adjusted=None,
                )

        return valid

    def _deduplicate_entities(self, entities: List[Entity]) -> List[Entity]:
        """
        Remove overlapping entities, keeping the one with highest confidence.

        Args:
            entities: List of entities (may overlap)

        Returns:
            Deduplicated list
        """
        if not entities:
            return []

        # Sort by confidence descending
        sorted_entities = sorted(entities, key=lambda e: e.confidence, reverse=True)

        result = []
        covered_ranges: List[tuple] = []

        for entity in sorted_entities:
            # Check if this entity overlaps with any already selected
            overlaps = False
            for start, end in covered_ranges:
                if entity.start < end and entity.end > start:
                    overlaps = True
                    break

            if not overlaps:
                result.append(entity)
                covered_ranges.append((entity.start, entity.end))

        return result

    def anonymize(
        self, text: str, session_ttl_hours: int = 24, threshold: float = 0.25
    ) -> AnonymizeResult:
        """
        Anonymize PII in text by replacing with placeholders.

        Args:
            text: Text to anonymize
            session_ttl_hours: How long to keep the session (for restoration)
            threshold: Minimum confidence for detection

        Returns:
            AnonymizeResult with anonymized text, mappings, and session info
        """
        # Detect entities
        entities = self.detect(text, threshold)

        # Generate session ID
        session_id = str(uuid.uuid4())

        if not entities:
            # No entities found, create session anyway for consistency
            self.db.create_session(
                session_id=session_id,
                original_text=text,
                anonymized_text=text,
                mappings={},
                entities=[],
                ttl_hours=session_ttl_hours,
            )

            return AnonymizeResult(
                session_id=session_id,
                anonymized_text=text,
                mappings={},
                entity_count=0,
                entities=[],
            )

        # Create placeholders and mappings
        mappings: Dict[str, str] = {}
        type_counters: Dict[str, int] = {}

        # Sort entities by start position (descending) for safe replacement
        sorted_entities = sorted(entities, key=lambda e: e.start, reverse=True)

        anonymized_text = text

        for entity in sorted_entities:
            # Generate placeholder name
            type_upper = entity.type.upper()
            if type_upper not in type_counters:
                type_counters[type_upper] = 0
            type_counters[type_upper] += 1

            placeholder = f"[{type_upper}_{type_counters[type_upper]}]"

            # Store mapping
            mappings[placeholder] = entity.text

            # Replace in text (from end to start to preserve positions)
            anonymized_text = (
                anonymized_text[: entity.start]
                + placeholder
                + anonymized_text[entity.end :]
            )

        # Fix counter order (we processed in reverse, so renumber)
        # Reprocess with correct numbering
        type_counters_final: Dict[str, int] = {}
        mappings_final: Dict[str, str] = {}

        # Re-sort by start position ascending
        sorted_entities_forward = sorted(entities, key=lambda e: e.start)
        anonymized_text = text

        # First pass: assign correct placeholder numbers
        placeholder_assignments: List[tuple] = []
        for entity in sorted_entities_forward:
            type_upper = entity.type.upper()
            if type_upper not in type_counters_final:
                type_counters_final[type_upper] = 0
            type_counters_final[type_upper] += 1

            placeholder = f"[{type_upper}_{type_counters_final[type_upper]}]"
            placeholder_assignments.append((entity, placeholder))
            mappings_final[placeholder] = entity.text

        # Second pass: replace from end to start
        for entity, placeholder in reversed(placeholder_assignments):
            anonymized_text = (
                anonymized_text[: entity.start]
                + placeholder
                + anonymized_text[entity.end :]
            )

        # Create session with detailed mapping info for db
        mappings_for_db: Dict[str, Dict[str, Any]] = {}
        for entity, placeholder in placeholder_assignments:
            mappings_for_db[placeholder] = {
                "original": entity.text,
                "type": entity.type,
                "start": entity.start,
                "end": entity.end,
                "confidence": entity.confidence,
                "validator_results": entity.validator_results,
            }

        self.db.create_session(
            session_id=session_id,
            original_text=text,
            anonymized_text=anonymized_text,
            mappings=mappings_for_db,
            entities=[
                {
                    "text": e.text,
                    "type": e.type,
                    "start": e.start,
                    "end": e.end,
                    "confidence": e.confidence,
                }
                for e in entities
            ],
            ttl_hours=session_ttl_hours,
        )

        return AnonymizeResult(
            session_id=session_id,
            anonymized_text=anonymized_text,
            mappings=mappings_final,
            entity_count=len(entities),
            entities=entities,
        )

    def restore(
        self, text: str, session_id: Optional[str] = None
    ) -> RestoreResult:
        """
        Restore original values from placeholders.

        Args:
            text: Text with placeholders (e.g., from LLM output)
            session_id: Optional session ID to use for mappings

        Returns:
            RestoreResult with restored text and mapping count
        """
        # Extract placeholders from text
        placeholders = self.PLACEHOLDER_PATTERN.findall(text)

        if not placeholders:
            return RestoreResult(
                restored_text=text,
                mappings_applied=0,
                session_id=session_id,
            )

        # Convert to full placeholder format
        placeholder_strings = [f"[{type_}_{num}]" for type_, num in placeholders]

        # Get mappings
        if session_id:
            mappings = self.db.get_session_mappings(session_id)
            if mappings is None:
                mappings = {}
        else:
            # Global lookup across all sessions
            mappings = self.db.find_mappings_for_placeholders(placeholder_strings)

        if not mappings:
            return RestoreResult(
                restored_text=text,
                mappings_applied=0,
                session_id=session_id,
            )

        # Replace placeholders with original values
        # Sort by length descending to handle nested placeholders correctly
        sorted_placeholders = sorted(mappings.keys(), key=len, reverse=True)

        restored_text = text
        mappings_applied = 0

        for placeholder in sorted_placeholders:
            original = mappings.get(placeholder)
            if original and placeholder in restored_text:
                restored_text = restored_text.replace(placeholder, original)
                mappings_applied += 1

        # Mark session as restored if session_id was provided
        if session_id:
            self.db.mark_session_restored(session_id)

        return RestoreResult(
            restored_text=restored_text,
            mappings_applied=mappings_applied,
            session_id=session_id,
        )

    # ==================== Convenience Methods ====================

    def get_stats(self) -> Dict[str, Any]:
        """
        Get database statistics.

        Returns:
            Dict with session count, mapping count, etc.
        """
        return self.db.get_stats()

    def cleanup(self) -> None:
        """
        Run cleanup operations on the database.

        Removes expired sessions and old detection logs.
        """
        self.db.cleanup_expired()
        self.db.cleanup_old_logs()

    def wipe_all(self) -> Dict[str, int]:
        """
        Completely reset the database.

        Returns:
            Dict with counts of deleted records
        """
        return self.db.wipe_all()
