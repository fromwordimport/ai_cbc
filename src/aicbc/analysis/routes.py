"""Analysis API routes — conjoint modeling, WTP, market simulation.

Model fitting is offloaded to Celery workers (``aicbc.analysis.tasks``)
so CPU-intensive NUTS sampling never blocks the FastAPI event loop.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from aicbc.analysis.models import (
    AnalyzeRequest,
    AnalysisJobStatus,
    AnalysisResultResponse,
    ConvergenceDiagnostics,
    ImportanceResponse,
    ImportanceStats,
    LatentClassRequest,
    LatentClassResponse,
    MarketSimRequest,
    MarketSimResponse,
    ParseScenarioRequest,
    PerAttributeTest,
    PriceCoefficientSummary,
    ProductScenario,
    ScenarioShare,
    SegmentComparisonResponse,
    WTPAttribute,
    WTPComparison,
    WTPResponse,
)
from aicbc.analysis.nl_scenario_parser import parse_nl_scenario
from aicbc.analysis.report_builder import build_report
from aicbc.analysis.cbc_visualizer import (
    build_dashboard_option,
    build_importance_chart_option,
    build_importance_pie_option,
    build_market_share_option,
    build_utility_distribution_option,
    build_wtp_chart_option,
)
from aicbc.analysis.preprocessing import get_feature_columns, to_long_format, validate_dataset
from aicbc.analysis.results.importance import aggregate_importance, compute_importance
from aicbc.analysis.results.segment_comparison import compare_segments as seg_compare
from aicbc.analysis.results.wtp import WTPCalculator
from aicbc.analysis.simulation.market_simulator import MarketSimulator
from aicbc.analysis.store import AnalysisStore, get_analysis_store
from aicbc.analysis.tasks import run_analysis_task, run_latent_class_task
from aicbc.core.store import get_questionnaire_store, get_response_store
from aicbc.questionnaire.models import Attribute, AttributeType
from aicbc.questionnaire.response_models import CBCRawDataset

router = APIRouter()
logger = structlog.get_logger("aicbc.api.analysis")


async def _verify_study_ownership(
    study_id: str, analysis_id: str, store: AnalysisStore
) -> None:
    """Verify that analysis_id belongs to study_id (isolation check).

    Prevents cross-study data access via manipulated URL paths.
    """
    result = await store.aget_result(analysis_id)
    if result is not None and result.study_id != study_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis '{analysis_id}' not found for study '{study_id}'",
        )


async def _get_study_attributes(study_id: str) -> list[Attribute]:
    """Retrieve study attributes from the questionnaire store."""
    store = get_questionnaire_store()
    study = await store.aget_study(study_id)
    if study is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Study '{study_id}' not found",
        )
    return study.attributes


async def _get_dataset(study_id: str) -> CBCRawDataset:
    """Retrieve the raw dataset for a study."""
    store = get_response_store()
    dataset = await store.aget_dataset(study_id)
    if dataset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No response dataset found for study '{study_id}'",
        )
    return dataset


# ---------------------------------------------------------------------------
# Job management
# ---------------------------------------------------------------------------


@router.post(
    "/studies/{study_id}/analyze",
    response_model=AnalysisJobStatus,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run conjoint analysis for a study (async)",
    response_description="Analysis job queued",
)
async def analyze_study(
    study_id: str,
    request: "AnalyzeRequest",
    analysis_store: AnalysisStore = Depends(get_analysis_store),
) -> AnalysisJobStatus:
    """Enqueue a conjoint analysis job for a study (HB/MNL/LatentClass).

    Model fitting is offloaded to a Celery worker so the API event loop
    is never blocked by CPU-intensive NUTS sampling.  The endpoint
    validates input data synchronously and returns ``202 Accepted``
    immediately.

    Use ``GET /studies/{study_id}/analysis/{analysis_id}/status`` to
    poll for progress.
    """
    log = logger.bind(study_id=study_id, model_type=request.model_type)
    log.info("analysis_requested")

    # ── Validate data synchronously (fast, errors returned immediately) ──
    attributes = await _get_study_attributes(study_id)
    dataset = await _get_dataset(study_id)

    validation = validate_dataset(dataset, attributes)
    if not validation["valid"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "errors": validation["errors"],
                "warnings": validation["warnings"],
            },
        )

    # ── Create QUEUED job ───────────────────────────────────────────────
    analysis_id = f"ar-{study_id}-{uuid.uuid4().hex[:8]}"
    job = AnalysisJobStatus(
        analysis_id=analysis_id,
        study_id=study_id,
        status="QUEUED",
        model_type=request.model_type,
        queued_at=datetime.now(UTC),
        started_at=None,
        estimated_duration_seconds=300 if request.model_type == "hb" else 600 if request.model_type == "latent_class" else 30,
        progress_percent=0.0,
    )
    await analysis_store.asave_job(job)

    # ── Enqueue Celery task ─────────────────────────────────────────────
    config_json = json.dumps({
        "n_draws": request.n_draws,
        "n_tune": request.n_tune,
        "n_chains": request.n_chains,
        "target_accept": request.target_accept,
        "n_classes": request.prior_config.get("n_classes", 3) if request.model_type == "latent_class" else None,
    })

    if request.model_type == "latent_class":
        result = run_latent_class_task.delay(
            study_id=study_id,
            analysis_id=analysis_id,
            config_json=config_json,
        )
    else:
        result = run_analysis_task.delay(
            study_id=study_id,
            analysis_id=analysis_id,
            model_type=request.model_type,
            config_json=config_json,
        )
    # Store Celery task_id for cross-process status tracking via AsyncResult
    job.metadata = {"celery_task_id": result.id}

    log.info("analysis_enqueued", analysis_id=analysis_id)
    return job


@router.get(
    "/studies/{study_id}/analysis/{analysis_id}",
    response_model=AnalysisResultResponse,
    summary="Get analysis result",
)
async def get_analysis_result(
    study_id: str,
    analysis_id: str,
    analysis_store: AnalysisStore = Depends(get_analysis_store),
) -> AnalysisResultResponse:
    """Retrieve a completed analysis result."""
    result = await analysis_store.aget_result(analysis_id)
    if result is None:
        # Check if job exists but hasn't completed yet → 409 Conflict
        job = await analysis_store.aget_job(analysis_id)
        if job is not None and job.status in ("QUEUED", "RUNNING", "PENDING"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Analysis '{analysis_id}' is still {job.status}. "
                       f"Retry when status is COMPLETED.",
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis result '{analysis_id}' not found",
        )
    await _verify_study_ownership(study_id, analysis_id, analysis_store)
    return result


@router.get(
    "/studies/{study_id}/analysis/{analysis_id}/status",
    response_model=AnalysisJobStatus,
    summary="Get analysis job status",
)
async def get_analysis_status(
    study_id: str,
    analysis_id: str,
    analysis_store: AnalysisStore = Depends(get_analysis_store),
) -> AnalysisJobStatus:
    """Poll for analysis job status."""
    job = await analysis_store.aget_job(analysis_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis job '{analysis_id}' not found",
        )
    if job.study_id != study_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis job '{analysis_id}' not found for study '{study_id}'",
        )

    # Bridge process isolation: check Celery backend for real task status.
    # The in-memory AnalysisStore is process-local; Celery's result backend
    # is the source of truth for cross-process task state.
    celery_task_id = job.metadata.get("celery_task_id")
    if job.status in ("QUEUED", "PENDING") and celery_task_id:
        from aicbc.analysis.tasks import celery_app
        try:
            task_result = celery_app.AsyncResult(celery_task_id)
            celery_state = task_result.state
            if celery_state == "STARTED":
                await analysis_store.aupdate_job_status(analysis_id, "RUNNING", progress=10.0)
                job.status = "RUNNING"
                if job.started_at is None:
                    job.started_at = datetime.now(UTC)
            elif celery_state == "SUCCESS":
                await analysis_store.aupdate_job_status(analysis_id, "COMPLETED", progress=100.0)
                job.status = "COMPLETED"
                if job.completed_at is None:
                    job.completed_at = datetime.now(UTC)
            elif celery_state == "FAILURE":
                await analysis_store.aupdate_job_status(analysis_id, "FAILED", progress=0.0)
                job.status = "FAILED"
        except Exception:
            pass  # Celery backend unavailable — fall through to store status

    # Zombie recovery: if RUNNING longer than hard timeout, mark FAILED
    _HARD_TIMEOUT = 600  # must match Celery task time_limit
    if job.status == "RUNNING" and job.started_at is not None:
        from datetime import UTC, datetime
        elapsed = (datetime.now(UTC) - job.started_at).total_seconds()
        if elapsed > _HARD_TIMEOUT:
            await analysis_store.aupdate_job_status(analysis_id, "FAILED", progress=0.0)
            job.status = "FAILED"

    return job


@router.get(
    "/studies/{study_id}/analysis",
    response_model=list[AnalysisJobStatus],
    summary="List analysis jobs for a study",
)
async def list_analyses(
    study_id: str,
    analysis_store: AnalysisStore = Depends(get_analysis_store),
) -> list[AnalysisJobStatus]:
    """List all analysis jobs associated with a study."""
    return await analysis_store.alist_jobs_by_study(study_id)


@router.delete(
    "/studies/{study_id}/analysis/{analysis_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an analysis job and its results",
)
async def delete_analysis(
    study_id: str,
    analysis_id: str,
    analysis_store: AnalysisStore = Depends(get_analysis_store),
) -> None:
    """Delete an analysis job and all derived artefacts."""
    job = await analysis_store.aget_job(analysis_id)
    if job is None or job.study_id != study_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis '{analysis_id}' not found for study '{study_id}'",
        )
    await analysis_store.adelete_analysis(analysis_id)


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


@router.get(
    "/studies/{study_id}/analysis/{analysis_id}/convergence",
    response_model=ConvergenceDiagnostics,
    summary="Get convergence diagnostics",
)
async def get_convergence(
    study_id: str,
    analysis_id: str,
    analysis_store: AnalysisStore = Depends(get_analysis_store),
) -> ConvergenceDiagnostics:
    """Get MCMC convergence diagnostics (R-hat, ESS)."""
    await _verify_study_ownership(study_id, analysis_id, analysis_store)
    diag = await analysis_store.aget_convergence(analysis_id)
    if diag is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Convergence diagnostics for '{analysis_id}' not found",
        )
    return diag


@router.get(
    "/studies/{study_id}/analysis/{analysis_id}/importance",
    response_model=ImportanceResponse,
    summary="Get attribute importance",
)
async def get_importance(
    study_id: str,
    analysis_id: str,
    analysis_store: AnalysisStore = Depends(get_analysis_store),
) -> ImportanceResponse:
    """Get attribute importance rankings and statistics."""
    await _verify_study_ownership(study_id, analysis_id, analysis_store)
    importance = await analysis_store.aget_importance(analysis_id)
    if importance is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Importance results for '{analysis_id}' not found",
        )
    return importance


@router.get(
    "/studies/{study_id}/analysis/{analysis_id}/wtp",
    response_model=WTPResponse,
    summary="Get willingness-to-pay estimates",
)
async def get_wtp(
    study_id: str,
    analysis_id: str,
    analysis_store: AnalysisStore = Depends(get_analysis_store),
) -> WTPResponse:
    """Get WTP estimates for all attributes."""
    await _verify_study_ownership(study_id, analysis_id, analysis_store)
    wtp = await analysis_store.aget_wtp(analysis_id)
    if wtp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"WTP results for '{analysis_id}' not found",
        )
    return wtp


# ---------------------------------------------------------------------------
# Market simulation
# ---------------------------------------------------------------------------


@router.post(
    "/studies/{study_id}/analysis/{analysis_id}/simulate-market",
    response_model=MarketSimResponse,
    summary="Simulate market shares",
)
async def simulate_market(
    study_id: str,
    analysis_id: str,
    request: MarketSimRequest,
    analysis_store: AnalysisStore = Depends(get_analysis_store),
) -> MarketSimResponse:
    """Simulate market shares for given product scenarios."""
    # Retrieve analysis result for utilities
    result = await analysis_store.aget_result(analysis_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis result '{analysis_id}' not found",
        )
    await _verify_study_ownership(study_id, analysis_id, analysis_store)

    # Get study attributes
    attributes = await _get_study_attributes(study_id)

    # Build utilities DataFrame with empty-guard
    import pandas as pd

    if not result.individual_utilities:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Analysis has no individual utility estimates",
        )
    util_df = pd.DataFrame.from_dict(
        result.individual_utilities, orient="index"
    )

    # Build scenarios dynamically from ProductScenario.attributes dict
    scenarios = [
        {"name": s.name, **s.attributes}
        for s in request.scenarios
    ]

    # Run simulation with error handling
    try:
        simulator = MarketSimulator(util_df, attributes)
        shares_df = simulator.simulate_share(
            scenarios,
            rule=request.rule,
            include_none=request.include_none,
            segment_filter=request.segment_filter,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Simulation error: {exc}",
        ) from exc

    response = MarketSimResponse(
        scenarios=[
            ScenarioShare(
                name=row["name"],
                predicted_share=row["predicted_share"],
                share_std=row.get("share_std", 0.0),
                share_ci_95_lower=row["share_ci_95_lower"],
                share_ci_95_upper=row["share_ci_95_upper"],
            )
            for _, row in shares_df.iterrows()
        ]
    )

    # Store result
    sim_id = uuid.uuid4().hex[:8]
    await analysis_store.asave_market_sim(analysis_id, sim_id, response)

    return response


# ---------------------------------------------------------------------------
# Segment comparison
# ---------------------------------------------------------------------------


@router.get(
    "/studies/{study_id}/analysis/{analysis_id}/segment-comparison",
    response_model=SegmentComparisonResponse,
    summary="Compare segments statistically",
)
async def compare_segments(
    study_id: str,
    analysis_id: str,
    segment_a: str = Query(..., description="First segment name"),
    segment_b: str = Query(..., description="Second segment name"),
    test_type: str = Query(
        default="welch",
        pattern=r"^(hotelling|welch|permutation)$",
    ),
    analysis_store: AnalysisStore = Depends(get_analysis_store),
) -> SegmentComparisonResponse:
    """Statistically compare preference differences between two segments.

    Supports Hotelling's T (multivariate), Welch's t-test (per-attribute),
    and permutation test (non-parametric).
    """
    # Retrieve analysis result for utilities
    result = await analysis_store.aget_result(analysis_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis result '{analysis_id}' not found",
        )
    await _verify_study_ownership(study_id, analysis_id, analysis_store)

    # Get dataset for segment labels
    dataset = await _get_dataset(study_id)

    # Build utilities DataFrame
    import pandas as pd

    util_df = pd.DataFrame.from_dict(
        result.individual_utilities, orient="index"
    )

    # Build segment labels series
    segment_map: dict[str, str] = {}
    for record in dataset.choice_records:
        segment_map[record.respondent_id] = record.segment
    segment_labels = pd.Series(segment_map)

    # Align indices
    common_ids = util_df.index.intersection(segment_labels.index)
    if len(common_ids) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No respondents found with both utilities and segment labels",
        )

    util_aligned = util_df.loc[common_ids]
    segment_aligned = segment_labels.loc[common_ids]

    # Validate segments
    if segment_a == segment_b:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="segment_a and segment_b must be different",
        )
    n_a = int((segment_aligned == segment_a).sum())
    n_b = int((segment_aligned == segment_b).sum())
    if n_a == 0 or n_b == 0:
        missing = segment_a if n_a == 0 else segment_b
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Segment '{missing}' has no respondents in the data",
        )

    # Run comparison
    comparison = seg_compare(
        util_aligned,
        segment_aligned,
        segment_a,
        segment_b,
        test_type,
    )

    # Build response
    overall = comparison["overall_test"]
    per_attr = [
        PerAttributeTest(
            attribute=r["attribute"],
            method=r["method"],
            t_statistic=r["t_statistic"],
            p_value=r["p_value"],
            significant=r["significant"],
            corrected_p_value=r.get("corrected_p_value"),
            corrected_significant=r.get("corrected_significant"),
            cohens_d=r["cohens_d"],
            effect_size=r["effect_size"],
            mean_a=r["mean_a"],
            mean_b=r["mean_b"],
        )
        for r in comparison["per_attribute"]
    ]

    response = SegmentComparisonResponse(
        segment_a=comparison["segment_a"],
        segment_b=comparison["segment_b"],
        n_a=comparison["n_a"],
        n_b=comparison["n_b"],
        overall_test={
            "method": overall["method"],
            "statistic": overall.get("statistic", overall.get("f_statistic", 0.0)),
            "p_value": overall["p_value"],
            "significant": overall["significant"],
        },
        per_attribute=per_attr,
        interpretation=comparison["interpretation"],
    )

    await analysis_store.asave_segment_comparison(
        analysis_id, segment_a, segment_b, response
    )
    return response


# ---------------------------------------------------------------------------
# Module 7: NL scenario parser, report builder, visualizer, latent class
# ---------------------------------------------------------------------------


@router.post(
    "/studies/{study_id}/parse-scenario",
    response_model=ProductScenario,
    summary="Parse a natural-language product description",
)
async def parse_scenario(
    study_id: str,
    request: ParseScenarioRequest,
) -> ProductScenario:
    """Convert free-text (e.g. '华为 2999 元嵌入式 13 套') into a ProductScenario."""
    attributes = await _get_study_attributes(study_id)
    return parse_nl_scenario(request.text, attributes)


@router.get(
    "/studies/{study_id}/analysis/{analysis_id}/report",
    summary="Download analysis report (Markdown or HTML)",
)
async def download_report(
    study_id: str,
    analysis_id: str,
    format: str = Query(default="markdown", pattern=r"^(markdown|html)$"),
    analysis_store: AnalysisStore = Depends(get_analysis_store),
) -> Response:
    """Return a human-readable CBC analysis report."""
    result = await analysis_store.aget_result(analysis_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis result '{analysis_id}' not found",
        )
    await _verify_study_ownership(study_id, analysis_id, analysis_store)

    importance = await analysis_store.aget_importance(analysis_id)
    wtp = await analysis_store.aget_wtp(analysis_id)
    market_sim = await analysis_store.aget_latest_market_sim(analysis_id)

    content = build_report(
        analysis_result=result,
        importance=importance,
        wtp=wtp,
        market_sim=market_sim,
        format=format,
    )
    media_type = "text/html" if format == "html" else "text/markdown; charset=utf-8"
    return Response(content=content, media_type=media_type)


@router.get(
    "/studies/{study_id}/analysis/{analysis_id}/visualization",
    summary="Get ECharts option for a selected chart",
)
async def get_visualization(
    study_id: str,
    analysis_id: str,
    chart: str = Query(
        ...,
        pattern=r"^(importance_bar|importance_pie|utility_distribution|market_share|wtp|dashboard)$",
    ),
    sim_id: str | None = Query(default=None, description="Market simulation ID (for market_share / dashboard)"),
    analysis_store: AnalysisStore = Depends(get_analysis_store),
) -> dict:
    """Return an ECharts-compatible JSON option for the requested chart."""
    result = await analysis_store.aget_result(analysis_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis result '{analysis_id}' not found",
        )
    await _verify_study_ownership(study_id, analysis_id, analysis_store)

    if chart == "importance_bar":
        importance = await analysis_store.aget_importance(analysis_id)
        return build_importance_chart_option(importance) if importance else {}

    if chart == "importance_pie":
        importance = await analysis_store.aget_importance(analysis_id)
        return build_importance_pie_option(importance) if importance else {}

    if chart == "utility_distribution":
        return build_utility_distribution_option(result.individual_utilities)

    if chart == "market_share":
        market_sim = await _get_market_sim(analysis_store, analysis_id, sim_id)
        return build_market_share_option(market_sim)

    if chart == "wtp":
        wtp = await analysis_store.aget_wtp(analysis_id)
        return build_wtp_chart_option(wtp) if wtp else {}

    # dashboard
    importance = await analysis_store.aget_importance(analysis_id)
    market_sim = await _get_market_sim(analysis_store, analysis_id, sim_id)
    return build_dashboard_option(importance, market_sim)


async def _get_market_sim(
    analysis_store: AnalysisStore,
    analysis_id: str,
    sim_id: str | None,
) -> MarketSimResponse | None:
    """Retrieve a market simulation, falling back to the latest saved one."""
    if sim_id:
        return await analysis_store.aget_market_sim(analysis_id, sim_id)
    return await analysis_store.aget_latest_market_sim(analysis_id)


@router.post(
    "/studies/{study_id}/analysis/latent-class",
    response_model=AnalysisJobStatus,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run latent class analysis for a study (async)",
)
async def run_latent_class(
    study_id: str,
    request: LatentClassRequest,
    analysis_store: AnalysisStore = Depends(get_analysis_store),
) -> AnalysisJobStatus:
    """Enqueue a latent class model fit for a study.

    Poll ``GET /studies/{study_id}/analysis/{analysis_id}/latent-class`` for
    the full result.
    """
    # Validate study exists (the Celery worker validates the dataset).
    await _get_study_attributes(study_id)

    analysis_id = f"lc-{study_id}-{uuid.uuid4().hex[:8]}"
    job = AnalysisJobStatus(
        analysis_id=analysis_id,
        study_id=study_id,
        status="QUEUED",
        model_type="latent_class",
        queued_at=datetime.now(UTC),
        started_at=None,
        estimated_duration_seconds=600,
        progress_percent=0.0,
    )
    await analysis_store.asave_job(job)

    config_json = json.dumps({
        "n_classes": request.n_classes,
        "n_draws": request.n_draws,
        "n_tune": request.n_tune,
        "n_chains": request.n_chains,
        "target_accept": request.target_accept,
    })
    celery_result = run_latent_class_task.delay(
        study_id=study_id,
        analysis_id=analysis_id,
        config_json=config_json,
    )
    job.metadata = {"celery_task_id": celery_result.id}
    return job


@router.get(
    "/studies/{study_id}/analysis/{analysis_id}/latent-class",
    response_model=LatentClassResponse,
    summary="Get latent class analysis result",
)
async def get_latent_class_result(
    study_id: str,
    analysis_id: str,
    analysis_store: AnalysisStore = Depends(get_analysis_store),
) -> LatentClassResponse:
    """Retrieve the full latent class model result."""
    result = await analysis_store.aget_latent_class_result(analysis_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Latent class result '{analysis_id}' not found",
        )
    if result.get("study_id") != study_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Latent class result '{analysis_id}' not found for study '{study_id}'",
        )
    return LatentClassResponse.model_validate(result)
