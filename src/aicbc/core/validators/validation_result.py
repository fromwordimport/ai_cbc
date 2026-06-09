"""Validation result data model."""

from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    """Result of a validation run.

    Attributes:
        passed: True if validation succeeded.
        errors: List of human-readable error messages.
        score: Optional numeric score (e.g. logic validator rule scores).
        details: Optional dict with per-rule or per-field detail.
    """

    passed: bool = True
    errors: list[str] = field(default_factory=list)
    score: float | None = None
    details: dict = field(default_factory=dict)

    def add_error(self, message: str) -> None:
        """Add an error message and mark as failed."""
        self.passed = False
        self.errors.append(message)

    def merge(self, other: "ValidationResult") -> "ValidationResult":
        """Merge another ValidationResult into this one."""
        if not other.passed:
            self.passed = False
        self.errors.extend(other.errors)
        self.details.update(other.details)
        return self
