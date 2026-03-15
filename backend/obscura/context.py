"""
Context analyzer for PII confidence adjustment.

Analyzes surrounding text to boost or penalize confidence scores
based on contextual signals like:
- "email:" before an email -> boost
- "@example.com" domain -> penalize
- "555" phone prefix -> penalize (fake numbers)
"""

import re
from typing import Any, Dict, List, Pattern


# Context signals for boosting or penalizing confidence
CONTEXT_SIGNALS: Dict[str, Dict[str, List[str]]] = {
    "boost": {
        "email": [
            r"(?:email|e-mail|mail)\s*(?:me|us|at|:)",
            r"(?:contact|reach|send)\s+(?:at|to)",
        ],
        "phone": [
            r"(?:call|text|reach|phone|mobile|cell)\s*(?:me|us|at|:)",
            r"(?:office|home|work|fax)\s*(?:number|#|:)",
        ],
        "government_id": [
            r"(?:ssn|social\s*security|passport|license)\s*(?:#|number|:)",
        ],
        "person_name": [
            r"(?:name|signed|from|by|author|contact)\s*:",
            r"(?:dear|hi|hello|attn)\s+",
            r"(?:mr|mrs|ms|dr|prof)\.?\s+",
        ],
        "financial_account": [
            r"(?:card|credit|debit|account)\s*(?:#|number|:)",
        ],
        "address": [
            r"(?:address|location|ship\s*to|mail\s*to)\s*:",
            r"(?:street|avenue|road|blvd)\b",
        ],
    },
    "penalize": {
        "person_name": [
            r"^[A-Z][A-Z\s]+:$",
            r"(?:placeholder|example|sample)",
        ],
        "email": [
            r"(?:enter|type|input)\s+(?:your|an?)\s+email",
            r"@example\.(?:com|org|net)",
        ],
        "phone": [
            r"555-?\d{3}-?\d{4}",  # 555 numbers are fake
        ],
        "__all__": [
            r"\[[A-Z_]+_\d+\]",  # Existing placeholders
            r"(?:example|sample|test|dummy|fake|placeholder)\b",
        ],
    },
}


class ContextAnalyzer:
    """
    Analyzes surrounding text context to adjust PII detection confidence.

    Uses pattern matching to identify contextual signals that indicate
    higher or lower likelihood of genuine PII.
    """

    # Adjustment values
    BOOST_PER_MATCH = 0.1
    PENALIZE_TYPE_SPECIFIC = -0.15
    PENALIZE_ALL = -0.2
    MAX_ADJUSTMENT = 0.3
    MIN_ADJUSTMENT = -0.3

    def __init__(self, window_size: int = 50):
        """
        Initialize the context analyzer.

        Args:
            window_size: Number of characters around entity to analyze
        """
        self.window_size = window_size
        self._boost_patterns = self._compile_patterns(CONTEXT_SIGNALS.get("boost", {}))
        self._penalize_patterns = self._compile_patterns(
            CONTEXT_SIGNALS.get("penalize", {})
        )

    def _compile_patterns(
        self, signals: Dict[str, List[str]]
    ) -> Dict[str, List[Pattern]]:
        """
        Compile regex patterns for performance.

        Args:
            signals: Dictionary of entity_type -> list of pattern strings

        Returns:
            Dictionary of entity_type -> list of compiled patterns
        """
        compiled: Dict[str, List[Pattern]] = {}
        for entity_type, patterns in signals.items():
            compiled[entity_type] = [
                re.compile(pattern, re.IGNORECASE) for pattern in patterns
            ]
        return compiled

    def analyze(self, entity: Any, full_text: str) -> float:
        """
        Analyze context around an entity and return confidence adjustment.

        Args:
            entity: Entity with .start, .end, .type attributes
            full_text: The complete text containing the entity

        Returns:
            Confidence adjustment in range [-0.3, +0.3]
        """
        # Handle edge cases
        if not full_text:
            return 0.0

        entity_type = getattr(entity, "type", None)
        start = getattr(entity, "start", 0)
        end = getattr(entity, "end", 0)

        # Validate entity bounds
        if start >= len(full_text) or end > len(full_text):
            return 0.0

        # Extract context window around entity
        context_start = max(0, start - self.window_size)
        context_end = min(len(full_text), end + self.window_size)
        context = full_text[context_start:context_end]

        if not context:
            return 0.0

        adjustment = 0.0

        # Apply boost patterns (one per category max to avoid double-counting)
        adjustment += self._apply_boost_patterns(entity_type, context)

        # Apply penalize patterns
        adjustment += self._apply_penalize_patterns(entity_type, context)

        # Clamp to valid range
        return max(self.MIN_ADJUSTMENT, min(self.MAX_ADJUSTMENT, adjustment))

    def _apply_boost_patterns(self, entity_type: str, context: str) -> float:
        """
        Check boost patterns and return positive adjustment.

        Only counts once per category to avoid over-boosting from
        multiple similar patterns.

        Args:
            entity_type: The entity type to check patterns for
            context: The context text to search

        Returns:
            Positive adjustment value
        """
        adjustment = 0.0

        # Get patterns for this entity type
        type_patterns = self._boost_patterns.get(entity_type, [])

        # Check each pattern, but only add boost once per category
        for pattern in type_patterns:
            if pattern.search(context):
                adjustment += self.BOOST_PER_MATCH
                break  # Only one boost per entity type's patterns

        return adjustment

    def _apply_penalize_patterns(self, entity_type: str, context: str) -> float:
        """
        Check penalize patterns and return negative adjustment.

        Applies type-specific penalties and __all__ penalties separately.

        Args:
            entity_type: The entity type to check patterns for
            context: The context text to search

        Returns:
            Negative adjustment value
        """
        adjustment = 0.0

        # Check type-specific penalize patterns
        type_patterns = self._penalize_patterns.get(entity_type, [])
        for pattern in type_patterns:
            if pattern.search(context):
                adjustment += self.PENALIZE_TYPE_SPECIFIC
                break  # Only one penalty per type-specific category

        # Check __all__ patterns (apply to all entity types)
        all_patterns = self._penalize_patterns.get("__all__", [])
        for pattern in all_patterns:
            if pattern.search(context):
                adjustment += self.PENALIZE_ALL
                break  # Only one penalty from __all__ category

        return adjustment
