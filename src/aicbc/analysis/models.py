"""Pydantic models for analysis API request/response payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Analysis job management
# ---------------------------------------------------------------------------


class AnalyzeRequest(BaseModel):
    """Request to run conjoint analysis for a study."""

    model_type: str = Field(
        default="hb",
        pattern=r"^(hb|mnl|latent_class)$",
        description="Statistical model type",
    )
    n_draws: int = Field(default=1000, ge=100, description="MCMC draws per chain")
    n_tune: int = Field(default=1000, ge=100, description="MCMC tuning iterations")
    n_chains: int = Field(default=4, ge=2, le=8, description="Number of parallel chains")
    target_accept: float = Field(default=0.9, ge=0.8, le=0.95)
    prior_config: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional prior configuration",
    )


class AnalysisJobStatus(BaseModel):
    """Status of an analysis job."""

    analysis_id: str
    study_id: str
    status: str = Field(
        pattern=r"^(PENDING|QUEUED|RUNNING|COMPLETED|FAILED|CANCELLED|TIMED_OUT)$"
    )
    model_type: str
    queued_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    estimated_duration_seconds: int
    progress_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    metadata: dict[str, str] = Field(
        default_factory=dict,
        description="Internal tracking data (celery_task_id, etc.)",
    )


# ---------------------------------------------------------------------------
# Convergence diagnostics
# ---------------------------------------------------------------------------


class ConvergenceDiagnostics(BaseModel):
    """MCMC convergence diagnostic results."""

    rhat_max: float
    rhat_by_param: dict[str, float]
    ess_bulk_min: float
    ess_tail_min: float
    ess_by_param: dict[str, float]
    converged: bool
    reliable_ess: bool
    divergences: int = 0
    tree_depth_max: int = 0


# ---------------------------------------------------------------------------
# Population parameters
# ---------------------------------------------------------------------------


class PopulationParams(BaseModel):
    """Population-level parameter estimates."""

    mu: dict[str, float]
    sigma: dict[str, float]


# ---------------------------------------------------------------------------
# Attribute importance
# ---------------------------------------------------------------------------


class ImportanceStats(BaseModel):
    """Statistics for a single attribute's importance."""

    mean: float
    std: float
    median: float
    min: float
    max: float
    q25: float
    q75: float
    ci_95_lower: float
    ci_95_upper: float


class ImportanceResponse(BaseModel):
    """Attribute importance results."""

    overall: dict[str, ImportanceStats]
    by_segment: dict[str, dict[str, ImportanceStats]] | None = None
    individual: dict[str, dict[str, float]] | None = Field(
        default=None,
        description="Per-respondent importance values (for box/violin plots)",
    )


# ---------------------------------------------------------------------------
# WTP (Willingness to Pay)
# ---------------------------------------------------------------------------


class WTPComparison(BaseModel):
    """WTP for a single level comparison."""

    from_level: str
    to_level: str
    wtp_mean: float
    wtp_median: float
    wtp_std: float
    ci_95_lower: float
    ci_95_upper: float
    n_valid: int


class WTPAttribute(BaseModel):
    """WTP results for a single attribute."""

    comparisons: list[WTPComparison]


class PriceCoefficientSummary(BaseModel):
    """Summary of price coefficient distribution."""

    mean: float
    median: float
    std: float
    negative_rate: float
    n_positive_outliers: int


class WTPResponse(BaseModel):
    """WTP calculation results."""

    wtp_values: dict[str, WTPAttribute]
    price_coefficient_summary: PriceCoefficientSummary


# ---------------------------------------------------------------------------
# Market simulation
# ---------------------------------------------------------------------------


class ProductScenario(BaseModel):
    """A single product configuration for market simulation.

    The ``attributes`` dict maps attribute IDs (matching the study's
    Attribute.id values) to their level values.  This makes the endpoint
    work with any product category, not just dishwasher.
    """

    name: str
    attributes: dict[str, Any] = Field(
        default_factory=dict,
        description="Attribute ID → level value (e.g. {'price': 3999, 'brand': '华为'})",
    )


class MarketSimRequest(BaseModel):
    """Request to simulate market shares."""

    scenarios: list[ProductScenario] = Field(..., min_length=2, max_length=10)
    rule: str = Field(default="logit", pattern=r"^(logit|first_choice)$")
    include_none: bool = True
    segment_filter: str | None = None


class ScenarioShare(BaseModel):
    """Predicted market share for a scenario."""

    name: str
    predicted_share: float
    share_std: float = 0.0
    share_ci_95_lower: float
    share_ci_95_upper: float


class MarketSimResponse(BaseModel):
    """Market simulation results."""

    scenarios: list[ScenarioShare]
    by_segment: dict[str, list[ScenarioShare]] | None = None


# ---------------------------------------------------------------------------
# Segment comparison
# ---------------------------------------------------------------------------


class OverallTestResult(BaseModel):
    """Overall multivariate test result."""

    method: str
    statistic: float
    p_value: float
    significant: bool


class PerAttributeTest(BaseModel):
    """Per-attribute univariate test result."""

    attribute: str
    method: str
    t_statistic: float
    p_value: float
    significant: bool
    corrected_p_value: float | None = None
    corrected_significant: bool | None = None
    cohens_d: float
    effect_size: str  # negligible, small, medium, large
    mean_a: float
    mean_b: float


class SegmentComparisonResponse(BaseModel):
    """Segment comparison statistical test results."""

    segment_a: str
    segment_b: str
    n_a: int
    n_b: int
    overall_test: OverallTestResult
    per_attribute: list[PerAttributeTest]
    interpretation: str


# ---------------------------------------------------------------------------
# Full analysis result
# ---------------------------------------------------------------------------


class AnalysisResultResponse(BaseModel):
    """Complete analysis result."""

    analysis_id: str
    study_id: str
    status: str
    model_type: str
    convergence: ConvergenceDiagnostics
    population_params: PopulationParams
    individual_utilities: dict[str, dict[str, float]]
    importance: dict[str, float]
    wtp: dict[str, Any]
    processing_time_seconds: float
    completed_at: datetime | None = None


# ---------------------------------------------------------------------------
# Module 7 helpers
# ---------------------------------------------------------------------------


class ParseScenarioRequest(BaseModel):
    """Request to parse a natural-language product description."""

    text: str = Field(..., min_length=1, max_length=2000)


class LatentClassRequest(BaseModel):
    """Request to fit a latent class model synchronously."""

    n_classes: int = Field(default=3, ge=2, le=6)
    n_draws: int = Field(default=500, ge=100, description="MCMC draws per chain")
    n_tune: int = Field(default=500, ge=100, description="MCMC tuning iterations")
    n_chains: int = Field(default=2, ge=2, le=8, description="Number of parallel chains")
    target_accept: float = Field(default=0.9, ge=0.8, le=0.95)


class LatentClassResponse(BaseModel):
    """Results from fitting a latent class model."""

    analysis_id: str
    study_id: str
    n_classes: int
    converged: bool
    rhat_max: float
    ess_bulk_min: int
    ess_tail_min: int
    class_probs: dict[str, float]
    class_utilities: dict[str, dict[str, float]]
    individual_class_probs: dict[str, dict[str, float]]
    assigned_class: dict[str, str]
    processing_time_seconds: float
    completed_at: datetime


# ---------------------------------------------------------------------------
# Error responses
# ---------------------------------------------------------------------------


class AnalysisError(BaseModel):
    """Standardized analysis error response."""

    error_code: str
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)
