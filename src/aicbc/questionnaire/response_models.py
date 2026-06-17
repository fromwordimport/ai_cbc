"""Response data models for CBC questionnaire answers.

Follows the CBCRawDataset and PersonaResponse schemas defined in
``docs/数据字典.md`` (sections 五 and 六).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class AlternativeRecord(BaseModel):
    """A single alternative within a choice record."""

    alt_index: int = Field(..., ge=0, description="Alternative index within the set")
    chosen: bool = Field(..., description="Whether this alternative was selected")
    attributes: dict[str, Any] = Field(
        ..., description="Attribute-level mapping {attribute_id: level_value}"
    )


class ChoiceRecord(BaseModel):
    """A single respondent's answer to one choice set."""

    respondent_id: str = Field(..., description="Persona / respondent identifier")
    respondent_index: int = Field(..., ge=0, description="0-based respondent index")
    segment: str = Field(..., description="Consumer segment")
    choice_set_id: int = Field(..., ge=1, description="Choice set ID (1-based)")
    choice_set_index: int = Field(..., ge=0, description="0-based choice set index")
    alternatives: list[AlternativeRecord] = Field(..., description="Alternative records")
    none_chosen: bool = Field(default=False, description="Whether 'none of these' was selected")


class DatasetMetadata(BaseModel):
    """Metadata for a CBCRawDataset."""

    study_id: str = Field(..., description="Study identifier")
    n_respondents: int = Field(..., ge=0, description="Number of respondents")
    n_choice_sets: int = Field(..., ge=1, description="Choice sets per respondent")
    n_alternatives: int = Field(..., ge=2, description="Alternatives per set (excl. none)")
    attributes: list[dict[str, Any]] = Field(
        default_factory=list, description="Attribute definitions"
    )


class CBCRawDataset(BaseModel):
    """Standardised exchange format: questionnaire output → analysis input."""

    metadata: DatasetMetadata = Field(..., description="Dataset-level metadata")
    choice_records: list[ChoiceRecord] = Field(
        default_factory=list, description="All choice records"
    )

    @property
    def n_records(self) -> int:
        """Total number of choice records."""
        return len(self.choice_records)

    def records_for_respondent(self, respondent_id: str) -> list[ChoiceRecord]:
        """Return all records for a given respondent."""
        return [r for r in self.choice_records if r.respondent_id == respondent_id]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to plain dictionary."""
        return self.model_dump(mode="json")


class SingleChoiceDetail(BaseModel):
    """Detailed response for one choice set (used inside PersonaResponse)."""

    choice_set_id: int = Field(..., description="Choice set ID")
    chosen_alt_index: int | None = Field(
        default=None, description="Selected alternative index, or None if 'none'"
    )
    reasoning: str = Field(default="", description="Brief reasoning for the choice")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence in the choice")


class PersonaResponse(BaseModel):
    """Complete answer record for a single virtual consumer."""

    response_id: str = Field(..., description="Unique response identifier")
    study_id: str = Field(..., description="Parent study identifier")
    persona_id: str = Field(..., description="Persona identifier (FK)")
    questionnaire_id: str = Field(..., description="Questionnaire identifier (FK)")
    responses: list[SingleChoiceDetail] = Field(
        default_factory=list, description="Per-choice-set answers"
    )
    completion_status: str = Field(
        default="COMPLETED",
        pattern=r"^(COMPLETED|PARTIAL|FAILED)$",
        description="Completion status",
    )
    authenticity_score: float | None = Field(
        default=None, ge=0, le=14, description="Answer authenticity score"
    )
    cost_cny: float = Field(default=0.0, ge=0, description="Simulation cost (CNY)")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Completion timestamp"
    )
