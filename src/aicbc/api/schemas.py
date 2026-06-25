"""Pydantic models for API request/response payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

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
    bias_failed_count: int = Field(
        default=0,
        description="Number of personas rejected due to bias audit failure",
    )
    bias_warning: str | None = Field(
        default=None,
        description="Bias audit warning when too many personas fail bias check (>=3)",
    )


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
            life_stage=profile.layer1_demographics.life_stage,
            city_tier=profile.layer1_demographics.city,
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


class PersonaExportResponse(BaseModel):
    """GDPR/PIPL-style data export for a single persona."""

    persona_id: str
    export_schema_version: str = "1.0"
    exported_at: datetime
    data_controller: str = Field(
        default="AI_CBC Platform",
        description="数据控制者名称",
    )
    data_subject_type: str = Field(
        default="virtual_consumer_profile",
        description="数据主体类型：虚拟消费者画像",
    )
    profile: dict[str, Any]
    generation_metadata: dict[str, Any]
    audit_trail: dict[str, Any]


class StudyExportResponse(BaseModel):
    """Complete data export for a study and its derived artefacts."""

    study_id: str
    export_schema_version: str = "1.0"
    exported_at: datetime
    data_controller: str = "AI_CBC Platform"
    study: dict[str, Any]
    questionnaire: dict[str, Any] | None
    personas: list[dict[str, Any]]
    responses: list[dict[str, Any]]
    dataset: dict[str, Any] | None
    analyses: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Behavior simulation
# ---------------------------------------------------------------------------


class ConverseRequest(BaseModel):
    """Request for a single conversational turn."""

    question: str = Field(..., max_length=2000, description="研究员的提问")
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

    questions: list[Annotated[str, Field(max_length=2000)]] = Field(
        ..., min_length=1, max_length=20, description="访谈问题列表"
    )
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


# ---------------------------------------------------------------------------
# Admin / audit log
# ---------------------------------------------------------------------------


class AuditLogEntry(BaseModel):
    """A single audit log entry."""

    timestamp: datetime
    user_id: str
    action: str
    resource: str
    resource_id: str
    result: str
    ip_address: str
    data: dict[str, Any]


class AuditLogListResponse(BaseModel):
    """Paginated audit log query response."""

    total: int
    page: int
    page_size: int
    entries: list[AuditLogEntry]


# ---------------------------------------------------------------------------
# CBC Studies
# ---------------------------------------------------------------------------


class CreateStudyRequest(BaseModel):
    """Request to create a new CBC study."""

    study_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z0-9_\-]+$",
        description="Unique study identifier (alphanumeric, hyphens, underscores)",
    )
    product_category: str = Field(..., description="Product category")
    research_goal: str = Field(..., description="Research objective")
    target_segments: list[str] = Field(default_factory=list, description="Target consumer segments")
    attributes: list[dict[str, Any]] | None = Field(
        default=None,
        description="Custom product attributes (defaults to dishwasher if None)",
    )
    design_parameters: dict[str, Any] | None = Field(
        default=None,
        description="Custom design parameters (defaults to 12 sets × 3 alts if None)",
    )


class StudyUpdateRequest(BaseModel):
    """Request to update an existing CBC study."""

    product_category: str | None = None
    research_goal: str | None = None
    target_segments: list[str] | None = None
    sample_size: int | None = Field(default=None, ge=30)
    cost_budget_cny: float | None = Field(default=None, ge=0)
    design_parameters: dict[str, Any] | None = None


class StudyDesignResponse(BaseModel):
    """Response for study attribute design."""

    study_id: str
    attributes: list[dict[str, Any]]  # 直接序列化后的 Attribute 字典
    prohibited_pairs: list[dict[str, Any]] = Field(default_factory=list)


class UpdateStudyDesignRequest(BaseModel):
    """Request to update study attributes."""

    attributes: list[dict[str, Any]]
    prohibited_pairs: list[dict[str, Any]] = Field(default_factory=list)


class StudySummary(BaseModel):
    """Light-weight study representation for list views."""

    study_id: str
    product_category: str
    research_goal: str
    target_segments: list[str] = Field(default_factory=list)
    status: str
    created_at: datetime

    @classmethod
    def from_study(cls, study: Any) -> StudySummary:
        """Build a summary from a CBCStudy."""
        return cls(
            study_id=study.study_id,
            product_category=study.product_category,
            research_goal=study.research_goal,
            target_segments=study.target_segments,
            status=study.status.value,
            created_at=study.created_at,
        )


class StudyDetailResponse(BaseModel):
    """Full study definition response."""

    study_id: str
    product_category: str
    research_goal: str
    target_segments: list[str]
    sample_size: int
    cost_budget_cny: float
    status: str
    attributes: list[dict[str, Any]]
    n_attributes: int
    n_choice_sets: int
    n_alternatives: int
    algorithm: str
    include_none: bool
    created_at: datetime

    @classmethod
    def from_study(cls, study: Any) -> StudyDetailResponse:
        """Build a detail response from a CBCStudy."""
        return cls(
            study_id=study.study_id,
            product_category=study.product_category,
            research_goal=study.research_goal,
            target_segments=study.target_segments,
            sample_size=getattr(study, "sample_size", 200),
            cost_budget_cny=getattr(study, "cost_budget_cny", 50.0),
            status=study.status.value,
            attributes=[a.model_dump(mode="json") for a in study.attributes],
            n_attributes=len(study.attributes),
            n_choice_sets=study.design_parameters.n_choice_sets,
            n_alternatives=study.design_parameters.n_alternatives,
            algorithm=study.design_parameters.algorithm.value,
            include_none=study.design_parameters.include_none,
            created_at=study.created_at,
        )


class StudyListResponse(BaseModel):
    """Response for study list queries."""

    total: int
    page: int
    page_size: int
    studies: list[StudySummary]


# ---------------------------------------------------------------------------
# CBC Questionnaires
# ---------------------------------------------------------------------------


class AlternativeView(BaseModel):
    """A single alternative in a choice set."""

    alt_index: int
    attributes: dict[str, Any]


class ChoiceSetView(BaseModel):
    """A single choice set (question)."""

    choice_set_id: int
    alternatives: list[AlternativeView]


class GenerateQuestionnaireResponse(BaseModel):
    """Response for questionnaire generation."""

    study_id: str
    questionnaire_id: str
    algorithm: str
    d_efficiency: float | None
    a_efficiency: float | None
    n_choice_sets: int
    n_alternatives: int
    include_none: bool
    validation_passed: bool
    validation_errors: list[str]


class DesignParametersView(BaseModel):
    """Experimental design parameters for a questionnaire."""

    algorithm: str
    d_efficiency: float | None
    a_efficiency: float | None
    n_attributes: int
    n_choice_sets: int
    n_alternatives: int
    include_none: bool


class QuestionnaireDetailResponse(BaseModel):
    """Full questionnaire with all choice sets."""

    questionnaire_id: str
    study_id: str
    design_params: DesignParametersView
    choice_sets: list[ChoiceSetView]
    created_at: datetime

    @classmethod
    def from_questionnaire(cls, q: Any) -> QuestionnaireDetailResponse:
        """Build a detail response from a CBCQuestionnaire."""
        return cls(
            questionnaire_id=q.questionnaire_id,
            study_id=q.study_id,
            design_params=DesignParametersView(
                algorithm=q.design_parameters.algorithm.value,
                d_efficiency=q.d_efficiency,
                a_efficiency=q.a_efficiency,
                n_attributes=len(q.attributes),
                n_choice_sets=len(q.choice_sets),
                n_alternatives=q.design_parameters.n_alternatives,
                include_none=q.design_parameters.include_none,
            ),
            choice_sets=[
                ChoiceSetView(
                    choice_set_id=cs.choice_set_id,
                    alternatives=[
                        AlternativeView(
                            alt_index=alt.alt_index,
                            attributes=alt.attributes,
                        )
                        for alt in cs.alternatives
                    ],
                )
                for cs in q.choice_sets
            ],
            created_at=q.created_at,
        )


# ---------------------------------------------------------------------------
# Response simulation
# ---------------------------------------------------------------------------


class SimulateResponsesRequest(BaseModel):
    """Request to simulate persona responses for a study."""

    persona_ids: list[str] = Field(
        ..., min_length=1, max_length=100, description="List of persona IDs to simulate"
    )
    deterministic: bool = Field(
        default=False, description="If True, always pick max-utility option (rule mode only)"
    )
    seed: int | None = Field(default=None, description="Random seed for reproducibility")
    mode: str = Field(
        default="rule",
        pattern=r"^(rule|llm)$",
        description="Simulation mode: 'rule' (fast, deterministic) or 'llm' (human-like, slower)",
    )


class SimulatedResponseSummary(BaseModel):
    """Summary of a single simulated response."""

    persona_id: str
    response_id: str
    completion_status: str
    n_choice_sets_answered: int


class SimulateResponsesResponse(BaseModel):
    """Response for batch response simulation."""

    study_id: str
    questionnaire_id: str
    simulated: int
    failed: int
    summaries: list[SimulatedResponseSummary]


class RawDatasetExportResponse(BaseModel):
    """CBCRawDataset export response."""

    study_id: str
    n_respondents: int
    n_choice_sets: int
    n_alternatives: int
    n_total_records: int
    choice_records: list[dict[str, Any]]


class PersonaResponseSummary(BaseModel):
    """Light-weight response representation for list views."""

    response_id: str
    persona_id: str
    completion_status: str
    n_answers: int
    created_at: datetime


class AsyncBatchGenerateResponse(BaseModel):
    """Response for async persona generation request."""

    job_id: str
    study_id: str
    requested: int
    status: str
    message: str


class PersonaGenerationJobStatusResponse(BaseModel):
    """Status of an async persona generation job."""

    job_id: str
    study_id: str
    status: str
    requested: int
    generated: int
    failed: int
    total_cost_cny: float
    progress: float
    bias_failed_count: int = 0
    bias_warning: str | None = None
    created_at: datetime
    updated_at: datetime
