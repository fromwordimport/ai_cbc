"""PlausibilityValidator — checks whether a persona's product context is realistic."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
import yaml

from aicbc.core.models.persona import PersonaProfile
from aicbc.core.validators.plausibility_models import PlausibilityFinding, PlausibilityResult
from aicbc.core.validators.product_context_models import DerivedProductContext

logger = structlog.get_logger("aicbc.validators")

DEFAULT_RULES_PATH = Path(__file__).parents[4] / "configs" / "plausibility_rules" / "default.yaml"


class PlausibilityValidator:
    """Validate that a persona's product context matches their life situation."""

    def __init__(self, rules_path: Path | str | None = None) -> None:
        self._rules_path = Path(rules_path) if rules_path else DEFAULT_RULES_PATH
        self._rules = self._load_rules()

    def _load_rules(self) -> list[dict[str, Any]]:
        if not self._rules_path.exists():
            logger.warning("plausibility_rules_not_found", path=str(self._rules_path))
            return []
        with self._rules_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            return []
        rules = data.get("rules", [])
        if not isinstance(rules, list):
            return []
        return [rule for rule in rules if isinstance(rule, dict)]

    def validate(
        self,
        persona: PersonaProfile,
        derived_context: DerivedProductContext,
    ) -> PlausibilityResult:
        """Run all active rules against the persona and derived context."""
        findings: list[PlausibilityFinding] = []

        for rule in self._rules:
            if not rule.get("enabled", True):
                continue
            if self._matches(rule, persona, derived_context):
                findings.append(
                    PlausibilityFinding(
                        rule_id=rule["id"],
                        severity=rule["severity"],
                        message=rule["message"],
                    )
                )

        hard_failed = any(f.severity == "hard" for f in findings)
        return PlausibilityResult(
            passed=not hard_failed,
            hard_failed=hard_failed,
            findings=findings,
        )

    def _matches(
        self,
        rule: dict[str, Any],
        persona: PersonaProfile,
        derived_context: DerivedProductContext,
    ) -> bool:
        """Evaluate a single rule's conditions."""
        l1 = persona.layer1_demographics
        conditions = rule.get("conditions", {})

        for key, expected in conditions.items():
            if key == "life_stage_contains":
                if expected not in l1.life_stage:
                    return False
            elif key == "living_type_contains":
                if expected not in l1.living_type:
                    return False
            elif key == "income_contains":
                if expected not in l1.income:
                    return False
            elif key == "occupation_contains":
                if expected not in l1.occupation:
                    return False
            elif key == "eligibility":
                if derived_context.eligibility != expected:
                    return False
            elif key == "eligibility_not":
                if derived_context.eligibility == expected:
                    return False
            elif key == "price_above":
                # Price-threshold rules are not implemented in the initial version.
                continue
        return True
