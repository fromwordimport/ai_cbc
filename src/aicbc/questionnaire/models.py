"""Pydantic models for CBC questionnaire design."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AttributeType(StrEnum):
    """Supported attribute types for CBC analysis."""

    CATEGORICAL = "categorical"
    ORDINAL = "ordinal"
    CONTINUOUS = "continuous"
    PRICE = "price"


class DesignAlgorithm(StrEnum):
    """Experimental design algorithm options."""

    BALANCED = "balanced"
    D_OPTIMAL = "d_optimal"


class StudyStatus(StrEnum):
    """Lifecycle status of a CBC study."""

    INIT = "INIT"
    DESIGNING = "DESIGNING"
    READY = "READY"
    COMPLETED = "COMPLETED"


# ---------------------------------------------------------------------------
# Attribute definitions
# ---------------------------------------------------------------------------


class AttributeLevel(BaseModel):
    """A single level within an attribute."""

    value: Any = Field(..., description="Level value (string, number, etc.)")
    label: str = Field(..., description="Human-readable label")
    description: str | None = Field(default=None, description="Optional description")


class Attribute(BaseModel):
    """A product attribute with its levels."""

    id: str = Field(..., description="Unique identifier (e.g. 'brand', 'price')")
    name: str = Field(..., description="Human-readable name (e.g. '品牌')")
    type: AttributeType = Field(default=AttributeType.CATEGORICAL, description="Attribute type")
    levels: list[AttributeLevel] = Field(..., description="List of levels")
    description: str | None = Field(default=None, description="Optional description")

    @field_validator("id")
    @classmethod
    def _validate_id_format(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_\-]+$", v):
            raise ValueError(
                "attribute id must contain only letters, digits, underscores, or hyphens"
            )
        return v

    @field_validator("levels")
    @classmethod
    def _validate_levels_length(cls, v: list[AttributeLevel]) -> list[AttributeLevel]:
        if len(v) < 2:
            raise ValueError("each attribute must have at least 2 levels")
        return v


# ---------------------------------------------------------------------------
# Study and design parameters
# ---------------------------------------------------------------------------


class DesignParameters(BaseModel):
    """Parameters controlling the experimental design."""

    n_choice_sets: int = Field(
        default=12,
        ge=3,
        le=30,
        description="Number of choice sets per respondent",
    )
    n_alternatives: int = Field(
        default=3,
        ge=2,
        le=5,
        description="Number of alternatives per choice set (excluding 'none')",
    )
    algorithm: DesignAlgorithm = Field(
        default=DesignAlgorithm.D_OPTIMAL,
        description="Experimental design algorithm",
    )
    include_none: bool = Field(
        default=True,
        description="Whether to include a 'none of these' option",
    )
    seed: int | None = Field(
        default=None,
        description="Random seed for reproducible designs",
    )

    @field_validator("algorithm", mode="before")
    @classmethod
    def _normalize_legacy_algorithm(cls, v: Any) -> Any:
        if isinstance(v, str) and v.lower() == "orthogonal":
            return "balanced"
        return v


class Condition(BaseModel):
    """A single attribute-level constraint — one leg of a prohibited combination."""

    attribute_id: str = Field(..., description="Attribute identifier")
    level_value: Any = Field(..., description="Forbidden level value")


class ProhibitedPair(BaseModel):
    """One or more attribute-level conditions that must NOT appear together.

    ``conditions`` are AND-ed: *every* condition must match for a profile
    to be rejected.  Multiple ``ProhibitedPair`` entries in a study are
    OR-ed: any matching pair blocks the profile.
    """

    conditions: list[Condition] = Field(
        default_factory=list,
        min_length=1,
        description="AND-ed conditions; all must match to trigger rejection",
    )


class CBCStudy(BaseModel):
    """A complete CBC study definition."""

    study_id: str = Field(..., description="Unique study identifier")
    product_category: str = Field(..., description="Product category (e.g. '洗碗机')")
    research_goal: str = Field(..., description="Research objective")
    target_segments: list[str] = Field(default_factory=list, description="Target consumer segments")
    sample_size: int = Field(
        default=200,
        ge=30,
        description="Target number of respondents (required by cost fusing)",
    )
    cost_budget_cny: float = Field(
        default=50.0,
        ge=0,
        description="Per-study cost budget in CNY (used by cost fuse)",
    )
    attributes: list[Attribute] = Field(..., description="Product attributes")
    design_parameters: DesignParameters = Field(
        default_factory=DesignParameters, description="Experimental design parameters"
    )
    prohibited_pairs: list[ProhibitedPair] = Field(
        default_factory=list, description="Prohibited attribute-level combinations"
    )
    status: StudyStatus = Field(default=StudyStatus.INIT, description="Study lifecycle status")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Creation timestamp"
    )

    @field_validator("attributes")
    @classmethod
    def _validate_attribute_count(cls, v: list[Attribute]) -> list[Attribute]:
        if len(v) < 2:
            raise ValueError("CBC study must have at least 2 attributes")
        if len(v) > 8:
            raise ValueError("CBC study should not exceed 8 attributes")
        return v

    @model_validator(mode="after")
    def _validate_unique_attribute_ids(self) -> CBCStudy:
        ids = [attr.id for attr in self.attributes]
        if len(ids) != len(set(ids)):
            raise ValueError("attribute ids must be unique")
        return self


# ---------------------------------------------------------------------------
# Questionnaire output
# ---------------------------------------------------------------------------


class Alternative(BaseModel):
    """A single product alternative within a choice set."""

    alt_index: int = Field(..., ge=0, description="Alternative index within the set")
    attributes: dict[str, Any] = Field(
        ..., description="Attribute-level mapping {attribute_id: level_value}"
    )


class ChoiceSet(BaseModel):
    """A single choice task (set of alternatives)."""

    choice_set_id: int = Field(..., ge=1, description="Choice set number (1-based)")
    alternatives: list[Alternative] = Field(..., description="Product alternatives")


class CBCQuestionnaire(BaseModel):
    """A generated CBC questionnaire (collection of choice sets)."""

    questionnaire_id: str = Field(..., description="Unique questionnaire identifier")
    study_id: str = Field(..., description="Parent study identifier")
    attributes: list[Attribute] = Field(
        default_factory=list,
        description="Product attributes used in this questionnaire",
    )
    choice_sets: list[ChoiceSet] = Field(..., description="List of choice sets")
    design_parameters: DesignParameters = Field(..., description="Design parameters used")
    d_efficiency: float | None = Field(
        default=None, description="D-efficiency score (0-1, target >= 0.85)"
    )
    a_efficiency: float | None = Field(default=None, description="A-efficiency score (0-1)")
    iterations: int | None = Field(
        default=None, description="Number of optimization iterations performed"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Generation timestamp",
    )

    @model_validator(mode="after")
    def _validate_choice_set_count(self) -> CBCQuestionnaire:
        expected = self.design_parameters.n_choice_sets
        actual = len(self.choice_sets)
        if actual != expected:
            raise ValueError(f"expected {expected} choice sets, got {actual}")
        return self

    @model_validator(mode="after")
    def _validate_alternatives_per_set(self) -> CBCQuestionnaire:
        expected = self.design_parameters.n_alternatives
        for cs in self.choice_sets:
            actual = len(cs.alternatives)
            if actual != expected:
                raise ValueError(
                    f"choice_set {cs.choice_set_id}: expected {expected} alternatives, got {actual}"
                )
        return self
