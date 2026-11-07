"""Enumerations shared by the AI layer and (later) the database models."""

import enum


class ObservationCategory(str, enum.Enum):
    SECURITY = "security"
    BUG = "bug"
    ERROR_HANDLING = "error_handling"
    INPUT_VALIDATION = "input_validation"
    PERFORMANCE = "performance"
    BEST_PRACTICE = "best_practice"


class Confidence(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FixStatus(str, enum.Enum):
    """What was checked about an AI-generated fix. None of these means 'verified secure'."""

    SYNTAX_VALID = "syntax_valid"
    SYNTAX_INVALID = "syntax_invalid"
    NOT_CHECKED = "not_checked"
    NO_CHANGE = "no_change"
    INCOMPLETE = "incomplete"
    UNRESOLVED_PLACEHOLDER = "unresolved_placeholder"
