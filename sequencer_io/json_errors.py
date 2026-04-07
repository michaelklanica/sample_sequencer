class PatternJsonError(Exception):
    """Raised when JSON cannot be read or parsed."""


class PatternValidationError(Exception):
    """Raised when parsed JSON is structurally/semantically invalid."""
