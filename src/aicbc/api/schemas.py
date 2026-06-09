"""Pydantic models for API request/response payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from aicbc.core.models.persona import (
    DishwasherContext,
    Layer1Demographics,
    Layer2Behavior,
    Layer3Psychology,
    Layer4Scenarios,
)
from aicbc.core.validators.validation_result import ValidationResult

# ---------------------------------------------------------------------------
# Batch generation
# ---------------------------------------------------------------------------


class BatchGenerateRequest(BaseModel):
    """Request body for batch persona generation."""

    count: int = Field(
        ...,
        ge=1,
        le=100,
        description="Number of personas to generate (1-100)",
    )
    seed: int | None = Field(
        default=None,
        description="Optional random seed for reproducible generation",
    )
    study_id: str = Field(
        default="default",
        description="Study identifier prefix for persona IDs",
    )
    skip_validation: bool = Field(
        default=False,
        description="If True, skip post-generation schema/logic validation",
    )


class GenerationErrorDetail(BaseModel):
    """Detail about a single failed persona generation."""

    index: int
    error: str


class BatchGenerateResponse(BaseModel):
    """Response body for batch persona generation."""

    study_id: str
    requested: int
    generated: int
    failed: int
    personas: list[PersonaSummary]
    errors: list[GenerationErrorDetail]
    total_cost_cny: float
    generation_time_seconds: float


# ---------------------------------------------------------------------------
# Persona summaries and detail views
# ---------------------------------------------------------------------------


class PersonaSummary(BaseModel):
    """Light-weight persona representation for list views."""

    persona_id: str
    segment: str
    life_stage: str
    city_tier: str
    income_bracket: str
    authenticity_score: float | None
    bias_audit_status: str
    created_at: datetime

    @classmethod
    def from_profile(cls, profile: Any) -> PersonaSummary:
        """Build a summary from a full PersonaProfile."""
        return cls(
            persona_id=profile.persona_id,
            segment=profile.segment,
            life_stage=profile.layer1_demographics.city,
            city_tier=profile.layer4_scenarios.daily_routine[:20] + "...",
            income_bracket=profile.layer1_demographics.income,
            authenticity_score=profile.authenticity_score,
            bias_audit_status=profile.bias_audit_status,
            created_at=profile.created_at,
        )


class PersonaDetail(BaseModel):
    """Full persona representation for detail views."""

    persona_id: str
    segment: str
    layer1_demographics: Layer1Demographics
    layer2_behavior: Layer2Behavior
    layer3_psychology: Layer3Psychology
    layer4_scenarios: Layer4Scenarios
    language_samples: list[str]
    dishwasher_context: DishwasherContext
    authenticity_score: float | None
    bias_audit_status: str
    generation_metadata: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_profile(cls, profile: Any) -> PersonaDetail:
        """Build a detail view from a full PersonaProfile."""
        return cls(
            persona_id=profile.persona_id,
            segment=profile.segment,
            layer1_demographics=profile.layer1_demographics,
            layer2_behavior=profile.layer2_behavior,
            layer3_psychology=profile.layer3_psychology,
            layer4_scenarios=profile.layer4_scenarios,
            language_samples=profile.language_samples,
            dishwasher_context=profile.dishwasher_context,
            authenticity_score=profile.authenticity_score,
            bias_audit_status=profile.bias_audit_status,
            generation_metadata=profile.generation_metadata.model_dump(mode="json"),
            created_at=profile.created_at,
        )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class ValidateResponse(BaseModel):
    """Response body for persona validation endpoint."""

    persona_id: str
    schema_passed: bool
    logic_passed: bool
    logic_score: float
    logic_max_score: float
    schema_errors: list[str]
    logic_errors: list[str]
    overall_passed: bool

    @classmethod
    def from_results(
        cls,
        persona_id: str,
        schema_result: ValidationResult,
        logic_result: ValidationResult,
    ) -> ValidateResponse:
        """Build validation response from two ValidationResult objects."""
        return cls(
            persona_id=persona_id,
            schema_passed=schema_result.passed,
            logic_passed=logic_result.passed,
            logic_score=logic_result.score,
            logic_max_score=logic_result.details.get("max_possible_score", 6.0),
            schema_errors=schema_result.errors,
            logic_errors=logic_result.errors,
            overall_passed=schema_result.passed and logic_result.passed,
        )


# ---------------------------------------------------------------------------
# Layer view
# ---------------------------------------------------------------------------


class LayerResponse(BaseModel):
    """Response for a single layer request."""

    persona_id: str
    layer_number: int
    layer_name: str
    data: dict[str, Any]


# ---------------------------------------------------------------------------
# List / query
# ---------------------------------------------------------------------------


class PersonaListResponse(BaseModel):
    """Response for persona list queries."""

    total: int
    page: int
    page_size: int
    personas: list[PersonaSummary]


class PersonaListQuery(BaseModel):
    """Query parameters for persona list endpoint."""

    study_id: str | None = None
    segment: str | None = None
    city_tier: str | None = None
    bias_status: str | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


# ---------------------------------------------------------------------------
# Behavior simulation
# ---------------------------------------------------------------------------


class ConverseRequest(BaseModel):
    """Request for a single conversational turn."""

    question: str = Field(..., description="研究员的提问")
    context: dict[str, Any] = Field(default_factory=dict, description="情境上下文")


class ConverseResponse(BaseModel):
    """Response for a single conversational turn."""

    persona_id: str
    turn_number: int
    researcher_question: str
    consumer_response: str
    emotion_tag: str
    inconsistency_flag: bool


class InterviewRequest(BaseModel):
    """Request for a multi-question interview."""

    questions: list[str] = Field(..., min_length=1, max_length=20, description="访谈问题列表")
    context: dict[str, Any] = Field(default_factory=dict, description="情境上下文")


class InterviewResponse(BaseModel):
    """Response for a multi-question interview."""

    persona_id: str
    turns: list[ConverseResponse]
    total_turns: int


class PurchaseDecisionRequest(BaseModel):
    """Request for purchase-decision simulation."""

    product_name: str = Field(..., description="产品名称")
    price_cny: float = Field(..., ge=0, description="产品价格（人民币）")
    core_selling_points: list[str] = Field(default_factory=list, description="核心卖点")


class PurchaseDecisionResponse(BaseModel):
    """Response for purchase-decision simulation."""

    persona_id: str
    product_name: str
    price_cny: float
    final_decision: str = Field(..., description="buy / not_buy / defer")
    confidence: float = Field(..., ge=0, le=1)
    stages: list[dict[str, Any]]
    stage_count: int
