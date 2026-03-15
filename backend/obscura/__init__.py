"""
Obscura - Detection Pipeline
Detect → Validate → Context → Correct → Persist
"""

__version__ = "1.0.0"

from obscura.database import DatabaseManager
from obscura.entity_types import ENTITY_LABELS, ENTITY_TYPES, DISPLAY_NAMES
from obscura.validators import (
    ValidationResult,
    ValidatorRegistry,
    LuhnValidator,
    CardPrefixValidator,
    SSNValidator,
    AadhaarValidator,
    NotLabelValidator,
    NotPlaceholderValidator,
    MinLengthValidator,
    BoundaryValidator,
    RFCEmailValidator,
    MinDigitsValidator,
)
from obscura.context import ContextAnalyzer, CONTEXT_SIGNALS
from obscura.corrections import CorrectionLayer, CorrectedEntity
from obscura.detector import PIIDetector, Entity, AnonymizeResult, RestoreResult

__all__ = [
    # Main detector class
    "PIIDetector",
    "Entity",
    "AnonymizeResult",
    "RestoreResult",
    # Database
    "DatabaseManager",
    # Entity types
    "ENTITY_TYPES",
    "ENTITY_LABELS",
    "DISPLAY_NAMES",
    # Validators
    "ValidationResult",
    "ValidatorRegistry",
    "LuhnValidator",
    "CardPrefixValidator",
    "SSNValidator",
    "AadhaarValidator",
    "NotLabelValidator",
    "NotPlaceholderValidator",
    "MinLengthValidator",
    "BoundaryValidator",
    "RFCEmailValidator",
    "MinDigitsValidator",
    # Context
    "ContextAnalyzer",
    "CONTEXT_SIGNALS",
    # Corrections
    "CorrectionLayer",
    "CorrectedEntity",
]
