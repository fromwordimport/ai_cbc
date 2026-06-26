"""Models for plausibility validation."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PlausibilityFinding:
    """A single plausibility issue."""

    rule_id: str
    severity: str  # "hard" | "soft"
    message: str


@dataclass
class PlausibilityResult:
    """Result of validating a persona's situational plausibility."""

    passed: bool
    hard_failed: bool
    findings: list[PlausibilityFinding] = field(default_factory=list)
