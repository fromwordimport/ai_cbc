"""SchemaValidator — structural and type validation for PersonaProfile."""

from aicbc.core.models.persona import PersonaProfile
from aicbc.core.validators.validation_result import ValidationResult


class SchemaValidator:
    """Validate PersonaProfile against schema constraints.

    Checks:
      - Required fields (persona_id, segment, layer1-4)
      - Enumerated values (gender, city)
      - Array lengths (language_samples, core_values)
      - Numeric ranges (authenticity_score)
      - String lengths (narrative_explanation)
    """

    VALID_GENDERS = ["男", "女", "其他"]
    VALID_CITIES = [
        "一线城市",
        "新一线城市",
        "二线城市",
        "三线城市",
        "四线城市",
        "五线城市",
        "县城/乡镇",
        "农村",
        "海外",
    ]

    def validate(self, persona: PersonaProfile) -> ValidationResult:
        """Run all schema validations and return a ValidationResult."""
        result = ValidationResult()

        self._check_required_fields(persona, result)
        self._check_enums(persona, result)
        self._check_array_lengths(persona, result)
        self._check_numeric_ranges(persona, result)
        self._check_string_lengths(persona, result)

        return result

    def _check_required_fields(self, persona: PersonaProfile, result: ValidationResult) -> None:
        """Ensure all mandatory fields are present and non-empty."""
        if not persona.persona_id or not persona.persona_id.strip():
            result.add_error("persona_id is required and must not be empty")

        if not persona.segment or not persona.segment.strip():
            result.add_error("segment is required and must not be empty")

        # Layer 1
        layer1 = persona.layer1_demographics
        for field_name in [
            "age",
            "gender",
            "city",
            "income",
            "occupation",
            "education",
            "marital_status",
            "living_type",
        ]:
            value = getattr(layer1, field_name, None)
            if value is None or (isinstance(value, str) and not value.strip()):
                result.add_error(
                    f"layer1_demographics.{field_name} is required and must not be empty"
                )

        # Layer 2
        layer2 = persona.layer2_behavior
        for field_name in ["price_sensitivity", "decision_style", "brand_loyalty"]:
            value = getattr(layer2, field_name, None)
            if value is None or (isinstance(value, str) and not value.strip()):
                result.add_error(f"layer2_behavior.{field_name} is required and must not be empty")

        # Layer 3
        layer3 = persona.layer3_psychology
        for field_name in ["secret_motivation", "defense_mechanism"]:
            value = getattr(layer3, field_name, None)
            if value is None or (isinstance(value, str) and not value.strip()):
                result.add_error(
                    f"layer3_psychology.{field_name} is required and must not be empty"
                )

        if layer3.tension_combination is None:
            result.add_error("layer3_psychology.tension_combination is required")

        # Layer 4
        layer4 = persona.layer4_scenarios
        for field_name in [
            "daily_routine",
            "purchase_trigger",
            "stress_response",
            "social_behavior",
        ]:
            value = getattr(layer4, field_name, None)
            if value is None or (isinstance(value, str) and not value.strip()):
                result.add_error(f"layer4_scenarios.{field_name} is required and must not be empty")

    def _check_enums(self, persona: PersonaProfile, result: ValidationResult) -> None:
        """Validate enumerated fields against allowed values."""
        layer1 = persona.layer1_demographics

        if layer1.gender not in self.VALID_GENDERS:
            result.add_error(
                f"layer1_demographics.gender must be one of {self.VALID_GENDERS}, "
                f"got '{layer1.gender}'"
            )

        if layer1.city not in self.VALID_CITIES:
            result.add_error(
                f"layer1_demographics.city must be one of {self.VALID_CITIES}, got '{layer1.city}'"
            )

    def _check_array_lengths(self, persona: PersonaProfile, result: ValidationResult) -> None:
        """Validate array fields have correct lengths."""
        if len(persona.language_samples) != 3:
            result.add_error(
                f"language_samples must contain exactly 3 items, got {len(persona.language_samples)}"
            )

        core_values = persona.layer3_psychology.core_values
        if len(core_values) < 1:
            result.add_error(
                f"layer3_psychology.core_values must contain at least 1 item, got {len(core_values)}"
            )

    def _check_numeric_ranges(self, persona: PersonaProfile, result: ValidationResult) -> None:
        """Validate numeric fields are within allowed ranges."""
        score = persona.authenticity_score
        if score is not None and not (0 <= score <= 14):
            result.add_error(f"authenticity_score must be between 0 and 14, got {score}")

    def _check_string_lengths(self, persona: PersonaProfile, result: ValidationResult) -> None:
        """Validate string fields meet minimum length requirements."""
        narrative = persona.layer3_psychology.tension_combination.narrative_explanation
        if narrative is not None:
            stripped = narrative.strip()
            if len(stripped) < 50:
                result.add_error(
                    f"layer3_psychology.tension_combination.narrative_explanation "
                    f"must be at least 50 characters, got {len(stripped)}"
                )

        # Check language_samples length (20-60 chars per sample)
        for i, sample in enumerate(persona.language_samples):
            stripped = sample.strip()
            if len(stripped) < 20:
                result.add_error(
                    f"language_samples[{i}] must be at least 20 characters, got {len(stripped)}"
                )
            if len(stripped) > 60:
                result.add_error(
                    f"language_samples[{i}] must be at most 60 characters, got {len(stripped)}"
                )
