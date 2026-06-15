"""Subsystem tool set — standardized tools for the AI_CBC three-subsystem pipeline.

Registers tools for:
  - Consumer Simulation: persona generation, batch simulation
  - CBC Questionnaire: experiment design, response collection
  - Data Analysis: model fitting (HB/MNL auto-select), importance, WTP, market sim

All tools use the ToolCalling Protocol (tool_protocol.py) and follow the
standard data exchange formats defined in docs/数据字典.md.

Data flow:
    PersonaProfile → CBCRawDataset → AnalysisResult
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import structlog

from aicbc.agents.tool_protocol import ToolRegistry, ToolResult, ToolSpec, tool
from aicbc.analysis.engines.hb_engine import HBConfig, HBEngine, HBResult
from aicbc.analysis.engines.mnl_engine import MNLEngine, MNLResult
from aicbc.analysis.models import (
    AnalysisResultResponse,
    ConvergenceDiagnostics,
    ImportanceResponse,
    ImportanceStats,
    PriceCoefficientSummary,
    WTPAttribute,
    WTPComparison,
    WTPResponse,
)
from aicbc.analysis.preprocessing import get_feature_columns, to_long_format, validate_dataset
from aicbc.analysis.results.importance import aggregate_importance, compute_importance
from aicbc.analysis.results.wtp import WTPCalculator
from aicbc.analysis.simulation.market_simulator import MarketSimulator
from aicbc.questionnaire.models import Attribute, AttributeType
from aicbc.questionnaire.response_models import CBCRawDataset

logger = structlog.get_logger("aicbc.agents.subsystem_tools")


# ---------------------------------------------------------------------------
# Model selection logic
# ---------------------------------------------------------------------------


def select_model_type(
    n_respondents: int,
    n_tasks_per_resp: int,
    min_resp_for_hb: int = 50,
    min_tasks_for_hb: int = 8,
) -> str:
    """Auto-select statistical model based on data characteristics.

    Rules:
        - n_resp >= 50 AND n_tasks >= 8 → HB (individual-level heterogeneity)
        - n_resp < 50 OR n_tasks < 8 → MNL (fast aggregate-level baseline)

    Args:
        n_respondents: Number of unique respondents.
        n_tasks_per_resp: Number of choice tasks per respondent.
        min_resp_for_hb: Minimum respondents for HB (default 50).
        min_tasks_for_hb: Minimum tasks per respondent for HB (default 8).

    Returns:
        "hb" or "mnl"
    """
    if n_respondents >= min_resp_for_hb and n_tasks_per_resp >= min_tasks_for_hb:
        return "hb"
    return "mnl"


# ---------------------------------------------------------------------------
# Analysis subsystem tools
# ---------------------------------------------------------------------------


def fit_conjoint_model(
    dataset: CBCRawDataset,
    attributes: list[Attribute],
    model_type: str | None = None,
    n_draws: int = 1000,
    n_tune: int = 1000,
    n_chains: int = 4,
    target_accept: float = 0.9,
    min_resp_for_hb: int = 50,
    min_tasks_for_hb: int = 8,
) -> dict[str, Any]:
    """Fit conjoint model (HB or MNL) with auto-selection.

    This is the primary analysis tool. It handles the full pipeline:
    validation → preprocessing → model fitting → convergence diagnostics.

    Args:
        dataset: Raw CBC response dataset.
        attributes: Ordered list of attribute definitions.
        model_type: "hb", "mnl", or None (auto-select).
        n_draws: MCMC draws per chain (HB only).
        n_tune: MCMC tuning iterations (HB only).
        n_chains: Number of parallel chains (HB only).
        target_accept: NUTS target acceptance rate (HB only).
        min_resp_for_hb: Threshold for auto-selecting HB.
        min_tasks_for_hb: Threshold for auto-selecting HB.

    Returns:
        Dict with keys:
            - model_type: "hb" or "mnl"
            - result: HBResult or MNLResult
            - converged: bool
            - diagnostics: dict (R-hat, ESS, divergences)
            - population_mu: dict[str, float]
            - population_sigma: dict[str, float]
            - individual_utilities: dict[str, dict[str, float]]
            - feature_cols: list[str]
            - processing_time_seconds: float
    """
    start = time.perf_counter()

    # 1. Validate
    validation = validate_dataset(dataset, attributes)
    if not validation["valid"]:
        raise ValueError(f"Dataset validation failed: {validation['errors']}")

    # 2. Preprocess
    df_long = to_long_format(dataset, attributes)
    feature_cols = get_feature_columns(attributes)

    # 3. Auto-select model
    if model_type is None:
        model_type = select_model_type(
            dataset.metadata.n_respondents,
            dataset.metadata.n_choice_sets,
            min_resp_for_hb,
            min_tasks_for_hb,
        )

    # 4. Fit model
    if model_type == "hb":
        config = HBConfig(
            n_draws=n_draws,
            n_tune=n_tune,
            n_chains=n_chains,
            target_accept=target_accept,
        )
        engine = HBEngine(config)
        result = engine.fit(df_long, feature_cols)
        converged = result.converged
        diagnostics = result.diagnostics or {}
    else:
        engine = MNLEngine()
        mnl_result = engine.fit(df_long, feature_cols)
        # Wrap as HBResult-compatible for downstream
        result = HBResult(
            converged=mnl_result.converged,
            rhat_max=1.0,
            ess_bulk_min=9999,
            ess_tail_min=9999,
            population_mu=mnl_result.population_mu,
            population_sigma=mnl_result.population_sigma,
            individual_utilities=mnl_result.individual_utilities,
            diagnostics={
                "rhat_max": 1.0,
                "ess_bulk_min": 9999,
                "converged": mnl_result.converged,
                "reliable_ess": True,
                "model_fit": {
                    "log_likelihood": mnl_result.log_likelihood,
                    "mc_fadden_r2": mnl_result.mc_fadden_r2,
                    "aic": mnl_result.aic,
                    "bic": mnl_result.bic,
                },
            },
        )
        converged = mnl_result.converged
        diagnostics = result.diagnostics

    processing_time = time.perf_counter() - start

    return {
        "model_type": model_type,
        "result": result,
        "converged": converged,
        "diagnostics": diagnostics,
        "population_mu": result.population_mu,
        "population_sigma": result.population_sigma,
        "individual_utilities": result.individual_utilities,
        "feature_cols": feature_cols,
        "processing_time_seconds": processing_time,
    }


def compute_attribute_importance(
    individual_utilities: dict[str, dict[str, float]],
    attributes: list[Attribute],
) -> dict[str, Any]:
    """Compute attribute importance from individual-level utilities.

    Args:
        individual_utilities: Dict mapping respondent_id → {param: utility}.
        attributes: Ordered list of attribute definitions.

    Returns:
        Dict with keys:
            - overall: dict[attr_id, dict[mean, std, ci_95_lower, ci_95_upper]]
            - ranking: list of (attr_id, mean_importance) sorted descending
    """
    util_df = pd.DataFrame.from_dict(individual_utilities, orient="index")
    importance_df = compute_importance(util_df, attributes)
    importance_agg = aggregate_importance(importance_df)

    overall = {}
    for attr_id, row in importance_agg.iterrows():
        overall[attr_id] = {
            "mean": float(row["mean"]),
            "std": float(row.get("std", 0.0)),
            "ci_95_lower": float(row.get("ci_95_lower", row["mean"])),
            "ci_95_upper": float(row.get("ci_95_upper", row["mean"])),
        }

    ranking = sorted(
        ((attr_id, data["mean"]) for attr_id, data in overall.items()),
        key=lambda x: x[1],
        reverse=True,
    )

    return {
        "overall": overall,
        "ranking": ranking,
    }


def compute_wtp(
    individual_utilities: dict[str, dict[str, float]],
    attributes: list[Attribute],
    price_attribute_id: str | None = None,
) -> dict[str, Any] | None:
    """Compute willingness-to-pay for all non-price attributes.

    Args:
        individual_utilities: Dict mapping respondent_id → {param: utility}.
        attributes: Ordered list of attribute definitions.
        price_attribute_id: ID of the price attribute. Auto-detected if None.

    Returns:
        Dict with WTP results per attribute, or None if no price attribute.
    """
    util_df = pd.DataFrame.from_dict(individual_utilities, orient="index")

    # Auto-detect price attribute
    if price_attribute_id is None:
        price_attrs = [a for a in attributes if a.type == AttributeType.PRICE]
        if not price_attrs:
            return None
        price_attribute_id = price_attrs[0].id

    if price_attribute_id not in util_df.columns:
        return None

    prices = [float(lv.value) for lv in price_attrs[0].levels]
    price_std = float(np.std(prices, ddof=0)) if len(prices) > 1 else 1.0
    wtp_calc = WTPCalculator(util_df, price_col=price_attribute_id, price_std=price_std)
    wtp_data = wtp_calc.compute_all_wtp(attributes)
    price_summary = wtp_calc.price_coefficient_summary()

    return {
        "wtp_values": wtp_data,
        "price_coefficient_summary": price_summary,
    }


def simulate_market_shares(
    individual_utilities: dict[str, dict[str, float]],
    attributes: list[Attribute],
    scenarios: list[dict[str, Any]],
    rule: str = "logit",
    include_none: bool = True,
) -> dict[str, Any]:
    """Simulate market shares for given product scenarios.

    Args:
        individual_utilities: Dict mapping respondent_id → {param: utility}.
        attributes: Ordered list of attribute definitions.
        scenarios: List of product profile dicts with feature values.
        rule: "logit" or "first_choice".
        include_none: Whether to include a "none" alternative.

    Returns:
        Dict with keys:
            - shares: list of {name, predicted_share, ci_95_lower, ci_95_upper}
            - rule: the simulation rule used
    """
    util_df = pd.DataFrame.from_dict(individual_utilities, orient="index")
    simulator = MarketSimulator(util_df, attributes)
    shares_df = simulator.simulate_share(
        scenarios,
        rule=rule,
        include_none=include_none,
    )

    shares = []
    for _, row in shares_df.iterrows():
        shares.append({
            "name": row["name"],
            "predicted_share": float(row["predicted_share"]),
            "share_ci_95_lower": float(row.get("share_ci_95_lower", row["predicted_share"])),
            "share_ci_95_upper": float(row.get("share_ci_95_upper", row["predicted_share"])),
        })

    return {
        "shares": shares,
        "rule": rule,
    }


def run_full_analysis(
    dataset: CBCRawDataset,
    attributes: list[Attribute],
    model_type: str | None = None,
    n_draws: int = 1000,
    n_tune: int = 1000,
    n_chains: int = 4,
    target_accept: float = 0.9,
) -> dict[str, Any]:
    """Run the complete analysis pipeline: model → importance → WTP.

    This is the high-level orchestration tool that chains together:
    fit_conjoint_model → compute_attribute_importance → compute_wtp.

    Args:
        dataset: Raw CBC response dataset.
        attributes: Ordered list of attribute definitions.
        model_type: "hb", "mnl", or None (auto-select).
        n_draws, n_tune, n_chains, target_accept: HB MCMC settings.

    Returns:
        Dict with keys:
            - analysis_result: AnalysisResultResponse (structured)
            - importance: attribute importance results
            - wtp: WTP results (or None)
            - warnings: list of warning strings
            - processing_time_seconds: total time
    """
    start = time.perf_counter()
    warnings: list[str] = []

    # 1. Fit model
    fit_result = fit_conjoint_model(
        dataset=dataset,
        attributes=attributes,
        model_type=model_type,
        n_draws=n_draws,
        n_tune=n_tune,
        n_chains=n_chains,
        target_accept=target_accept,
    )

    model_type = fit_result["model_type"]
    hb_result = fit_result["result"]

    # 2. Convergence check
    if not fit_result["converged"]:
        diag = fit_result["diagnostics"]
        rhat = diag.get("rhat_max", "N/A")
        warnings.append(f"模型未完全收敛 (R-hat max={rhat:.3f})。建议增加采样次数。")

    # 3. Price coefficient check
    price_attrs = [a for a in attributes if a.type == AttributeType.PRICE]
    if price_attrs:
        price_col = price_attrs[0].id
        if price_col in hb_result.population_mu and hb_result.population_mu[price_col] > 0:
            warnings.append(
                f"价格系数为正 ({hb_result.population_mu[price_col]:.4f})，"
                f"违背经济学直觉。建议检查数据编码或增加样本量。"
            )

    # 4. Importance
    importance = compute_attribute_importance(
        hb_result.individual_utilities,
        attributes,
    )

    # 5. WTP
    wtp = compute_wtp(hb_result.individual_utilities, attributes)

    # 6. Build structured result
    processing_time = time.perf_counter() - start

    diag = fit_result["diagnostics"]
    convergence = ConvergenceDiagnostics(
        rhat_max=hb_result.rhat_max,
        rhat_by_param=diag.get("rhat_by_param", {}),
        ess_bulk_min=hb_result.ess_bulk_min,
        ess_tail_min=hb_result.ess_tail_min,
        ess_by_param=diag.get("ess_by_param", {}),
        converged=fit_result["converged"],
        reliable_ess=diag.get("reliable_ess", False),
        divergences=diag.get("divergences", 0),
        tree_depth_max=diag.get("tree_depth_max", 0),
    )

    importance_dict = {attr_id: data["mean"] for attr_id, data in importance["overall"].items()}

    analysis_result = AnalysisResultResponse(
        analysis_id=f"auto-{dataset.metadata.study_id}",
        study_id=dataset.metadata.study_id,
        status="COMPLETED",
        model_type=model_type,
        convergence=convergence,
        population_params={
            "mu": hb_result.population_mu,
            "sigma": hb_result.population_sigma,
        },
        individual_utilities=hb_result.individual_utilities,
        importance=importance_dict,
        wtp=wtp or {},
        processing_time_seconds=processing_time,
    )

    return {
        "analysis_result": analysis_result,
        "importance": importance,
        "wtp": wtp,
        "warnings": warnings,
        "processing_time_seconds": processing_time,
    }


# ---------------------------------------------------------------------------
# Registry setup
# ---------------------------------------------------------------------------


def register_analysis_tools(registry: ToolRegistry | None = None) -> ToolRegistry:
    """Register all analysis subsystem tools.

    Returns:
        The populated ToolRegistry.
    """
    reg = registry or ToolRegistry.global_registry()

    reg.register(
        ToolSpec(
            name="fit_conjoint_model",
            description="Fit HB or MNL conjoint model with auto-selection",
            parameters=[
                ToolSpec._from_param("dataset", "CBCRawDataset object"),
                ToolSpec._from_param("attributes", "list of Attribute definitions"),
                ToolSpec._from_param("model_type", "'hb', 'mnl', or None (auto)", required=False),
                ToolSpec._from_param("n_draws", "MCMC draws per chain", required=False),
                ToolSpec._from_param("n_tune", "MCMC tuning iterations", required=False),
                ToolSpec._from_param("n_chains", "Number of chains", required=False),
                ToolSpec._from_param("target_accept", "Target acceptance rate", required=False),
            ],
            timeout_seconds=600.0,
            max_retries=1,
            tags=["analysis", "model"],
        ),
        fit_conjoint_model,
    )

    reg.register(
        ToolSpec(
            name="compute_attribute_importance",
            description="Compute attribute importance from individual utilities",
            parameters=[
                ToolSpec._from_param("individual_utilities", "Dict of respondent utilities"),
                ToolSpec._from_param("attributes", "list of Attribute definitions"),
            ],
            timeout_seconds=30.0,
            tags=["analysis", "importance"],
        ),
        compute_attribute_importance,
    )

    reg.register(
        ToolSpec(
            name="compute_wtp",
            description="Compute willingness-to-pay estimates",
            parameters=[
                ToolSpec._from_param("individual_utilities", "Dict of respondent utilities"),
                ToolSpec._from_param("attributes", "list of Attribute definitions"),
                ToolSpec._from_param("price_attribute_id", "ID of price attribute", required=False),
            ],
            timeout_seconds=30.0,
            tags=["analysis", "wtp"],
        ),
        compute_wtp,
    )

    reg.register(
        ToolSpec(
            name="simulate_market_shares",
            description="Simulate market shares for product scenarios",
            parameters=[
                ToolSpec._from_param("individual_utilities", "Dict of respondent utilities"),
                ToolSpec._from_param("attributes", "list of Attribute definitions"),
                ToolSpec._from_param("scenarios", "List of product profile dicts"),
                ToolSpec._from_param("rule", "'logit' or 'first_choice'", required=False),
                ToolSpec._from_param("include_none", "Include none alternative", required=False),
            ],
            timeout_seconds=60.0,
            tags=["analysis", "simulation"],
        ),
        simulate_market_shares,
    )

    reg.register(
        ToolSpec(
            name="run_full_analysis",
            description="Run complete analysis pipeline: model → importance → WTP",
            parameters=[
                ToolSpec._from_param("dataset", "CBCRawDataset object"),
                ToolSpec._from_param("attributes", "list of Attribute definitions"),
                ToolSpec._from_param("model_type", "'hb', 'mnl', or None (auto)", required=False),
                ToolSpec._from_param("n_draws", "MCMC draws", required=False),
                ToolSpec._from_param("n_tune", "MCMC tune", required=False),
                ToolSpec._from_param("n_chains", "Number of chains", required=False),
                ToolSpec._from_param("target_accept", "Target acceptance", required=False),
            ],
            timeout_seconds=900.0,
            max_retries=1,
            tags=["analysis", "pipeline"],
        ),
        run_full_analysis,
    )

    reg.register(
        ToolSpec(
            name="select_model_type",
            description="Auto-select HB or MNL based on sample size",
            parameters=[
                ToolSpec._from_param("n_respondents", "Number of respondents"),
                ToolSpec._from_param("n_tasks_per_resp", "Tasks per respondent"),
                ToolSpec._from_param("min_resp_for_hb", "HB threshold", required=False),
                ToolSpec._from_param("min_tasks_for_hb", "HB task threshold", required=False),
            ],
            timeout_seconds=5.0,
            tags=["analysis", "model_selection"],
        ),
        select_model_type,
    )

    logger.info("analysis_tools_registered", count=6)
    return reg


def _from_param(name: str, description: str, required: bool = True) -> Any:
    """Helper to create a ToolParameter (used in ToolSpec construction above)."""
    from aicbc.agents.tool_protocol import ToolParameter
    return ToolParameter(name=name, param_type="any", description=description, required=required)


# Monkey-patch the static method onto ToolSpec for use above
ToolSpec._from_param = staticmethod(_from_param)  # type: ignore


def get_default_tool_registry() -> ToolRegistry:
    """Get a fully populated default tool registry with all subsystem tools."""
    registry = ToolRegistry(name="aicbc_default")
    register_analysis_tools(registry)
    return registry
