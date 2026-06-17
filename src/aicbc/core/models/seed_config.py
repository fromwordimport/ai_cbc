"""SeedConfig Pydantic model for consumer seed generation."""

from typing import Any

from pydantic import BaseModel, Field, field_validator


class TensionPair(BaseModel):
    """A detected tension pair with its narrative explanation."""

    tag_a: str = Field(..., description="First tag in the tension pair")
    tag_b: str = Field(..., description="Second tag in the tension pair")
    tension_value: float = Field(..., description="Tension strength between 0 and 1")
    narrative: str = Field(default="", description="Psychological narrative explaining the tension")

    @field_validator("tension_value")
    @classmethod
    def clamp_tension(cls, v: float) -> float:
        """Clamp tension value to [0, 1]."""
        return max(0.0, min(1.0, v))


class SeedConfig(BaseModel):
    """Seed configuration for a virtual consumer persona.

    The seed is the foundational triad: life stage + core anxieties + income bracket,
    plus tension metadata that validates the configuration has narrative depth.
    """

    life_stage: str = Field(..., description="Life stage of the consumer (e.g., '初入职场单身')")
    anxieties: list[str] = Field(
        default_factory=list,
        min_length=1,
        max_length=3,
        description="Core anxiety labels matched to the life stage",
    )
    income_bracket: str = Field(..., description="Personal or household annual income bracket")
    city_tier: str = Field(
        ..., description="City tier (一线城市, 新一线城市, 二线城市, 三四线城市, 县城/乡镇)"
    )
    tension_score: float = Field(
        default=0.0,
        description="Overall tension score (0 = no tension, 1 = maximum tension)",
    )
    tension_pairs: list[TensionPair] = Field(
        default_factory=list,
        description="Detected contradictory tag combinations with tension values",
    )
    # Optional fields for downstream use
    extra_tags: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional sampled tags for persona enrichment",
    )

    @field_validator("tension_score")
    @classmethod
    def clamp_tension_score(cls, v: float) -> float:
        """Clamp tension score to [0, 1]."""
        return max(0.0, min(1.0, v))

    @field_validator("anxieties")
    @classmethod
    def validate_anxieties(cls, v: list[str]) -> list[str]:
        """Ensure anxieties list is not empty and deduplicated."""
        seen: set[str] = set()
        deduped: list[str] = []
        for item in v:
            if item not in seen:
                seen.add(item)
                deduped.append(item)
        if not deduped:
            raise ValueError("At least one anxiety must be provided")
        return deduped
