"""AnalysisAgent — automated conjoint analysis pipeline.

Orchestrates the full analysis workflow from raw CBC data to structured
results and natural-language interpretation. Designed to be callable by
an LLM agent or backend service.

Usage:
    agent = AnalysisAgent(config=AnalysisAgentConfig())
    result = agent.run(dataset, attributes)

The pipeline:
    1. Validate dataset quality
    2. Convert to long format with effects coding
    3. Fit HB model (or fallback to MNL for small samples)
    4. Convergence diagnostics (R-hat < 1.1, ESS > 400)
    5. Compute attribute importance
    6. Compute WTP (if price attribute present)
    7. Generate natural-language interpretation report
    8. Return structured AnalysisResult
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import structlog

from aicbc.analysis.engines.hb_engine import HBConfig, HBEngine, HBResult
from aicbc.analysis.engines.mnl_engine import MNLEngine
from aicbc.analysis.models import (
    AnalysisResultResponse,
    ConvergenceDiagnostics,
    PriceCoefficientSummary,
    WTPAttribute,
    WTPComparison,
    WTPResponse,
)
from aicbc.analysis.preprocessing import get_feature_columns, to_long_format, validate_dataset
from aicbc.analysis.results.importance import aggregate_importance, compute_importance
from aicbc.analysis.results.wtp import WTPCalculator
from aicbc.core.security.input_sanitizer import sanitize_text
from aicbc.questionnaire.models import Attribute, AttributeType
from aicbc.questionnaire.response_models import CBCRawDataset

logger = structlog.get_logger("aicbc.agents.analysis")


@dataclass
class AnalysisAgentConfig:
    """Configuration for the AnalysisAgent."""

    # Model selection thresholds
    min_resp_for_hb: int = 50
    min_tasks_per_resp: int = 8

    # HB MCMC settings
    hb_draws: int = 1000
    hb_tune: int = 1000
    hb_chains: int = 4
    hb_target_accept: float = 0.9

    # Convergence thresholds
    rhat_threshold: float = 1.1
    ess_min_threshold: int = 400

    # WTP filtering
    wtp_quantile_trim: float = 0.99

    # Reporting
    include_individual_utilities: bool = True
    max_report_attributes: int = 10

    def __post_init__(self) -> None:
        """Validate configuration values are within safe ranges."""
        if self.rhat_threshold < 1.0 or self.rhat_threshold > 1.5:
            raise ValueError(f"rhat_threshold must be in [1.0, 1.5], got {self.rhat_threshold}")
        if self.ess_min_threshold < 100:
            raise ValueError(f"ess_min_threshold must be >= 100, got {self.ess_min_threshold}")
        if self.hb_draws < 100:
            raise ValueError(f"hb_draws must be >= 100, got {self.hb_draws}")
        if self.hb_tune < 100:
            raise ValueError(f"hb_tune must be >= 100, got {self.hb_tune}")
        if self.hb_chains < 2 or self.hb_chains > 8:
            raise ValueError(f"hb_chains must be in [2, 8], got {self.hb_chains}")


@dataclass
class AnalysisReport:
    """Natural-language interpretation of analysis results."""

    summary: str
    key_findings: list[str]
    convergence_assessment: str
    warnings: list[str]
    recommendations: list[str]


class AnalysisAgent:
    """Automated conjoint analysis agent.

    Wraps the full pipeline from raw data to structured results + report.
    """

    def __init__(self, config: AnalysisAgentConfig | None = None) -> None:
        self.config = config or AnalysisAgentConfig()
        self._log = logger.bind(agent="AnalysisAgent")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        dataset: CBCRawDataset,
        attributes: list[Attribute],
    ) -> dict[str, Any]:
        """Run the full analysis pipeline.

        Args:
            dataset: Raw CBC response dataset.
            attributes: Ordered list of attribute definitions.

        Returns:
            Dict with keys:
                - result: AnalysisResultResponse (structured data)
                - report: AnalysisReport (natural language)
                - diagnostics: dict (raw convergence metrics)
                - warnings: list[str]
        """
        start_time = time.time()
        warnings: list[str] = []

        # 0. Sanitize inputs (SEC-012 defence-in-depth — AnalysisAgent does not
        #    inherit BaseAgent, so apply sanitization explicitly)
        for attr in attributes:
            attr.name = sanitize_text(attr.name, field_name="attribute_name")
        if dataset.metadata.study_id:
            _ = sanitize_text(dataset.metadata.study_id, field_name="study_id")

        # 1. Validate
        self._log.info("step_validate_dataset")
        validation = validate_dataset(dataset, attributes)
        if not validation["valid"]:
            raise ValueError(f"Dataset validation failed: {validation['errors']}")
        warnings.extend(validation.get("warnings", []))

        # 2. Preprocess
        self._log.info("step_preprocess")
        df_long = to_long_format(dataset, attributes)
        feature_cols = get_feature_columns(attributes)

        # 3. Auto-select model
        model_type = self._select_model(dataset)
        self._log.info("model_selected", model_type=model_type)

        # 4. Fit model (with one convergence retry if needed)
        self._log.info("step_fit_model", model_type=model_type)
        hb_result = self._fit_model(df_long, feature_cols, model_type)

        # 5. Convergence check — retry once with more samples if not converged
        converged = self._check_convergence(hb_result)
        if not converged and model_type == "hb":
            self._log.info("step_retry_fit_with_more_samples")
            hb_config_retry = HBConfig(
                n_draws=hb_result.diagnostics.get("draws", self.config.hb_draws) * 2,
                n_tune=hb_result.diagnostics.get("tune", self.config.hb_tune) * 2,
            )
            hb_engine_retry = HBEngine(hb_config_retry)
            hb_result = hb_engine_retry.fit(df_long, feature_cols)
            converged = self._check_convergence(hb_result)
        if not converged:
            warnings.append(
                f"模型未完全收敛 (R-hat max={hb_result.rhat_max:.3f} > "
                f"{self.config.rhat_threshold}). 建议增加采样次数。"
            )

        # 6. Price coefficient check
        price_warnings = self._check_price_coefficient(hb_result, attributes)
        warnings.extend(price_warnings)

        # 7. Compute importance
        self._log.info("step_compute_importance")
        util_df = pd.DataFrame.from_dict(hb_result.individual_utilities, orient="index")
        importance_df = compute_importance(util_df, attributes)
        importance_agg = aggregate_importance(importance_df)

        # 8. Compute WTP
        self._log.info("step_compute_wtp")
        wtp_resp, price_summary = self._compute_wtp(util_df, attributes)

        # 9. Build structured result
        processing_time = time.time() - start_time
        result = self._build_result(
            study_id=dataset.metadata.study_id,
            model_type=model_type,
            hb_result=hb_result,
            importance_agg=importance_agg,
            wtp_resp=wtp_resp,
            price_summary=price_summary,
            processing_time=processing_time,
        )

        # 10. Generate report
        report = self._generate_report(
            result=result,
            attributes=attributes,
            warnings=warnings,
        )

        self._log.info(
            "analysis_complete",
            study_id=dataset.metadata.study_id,
            converged=converged,
            processing_time=processing_time,
        )

        return {
            "result": result,
            "report": report,
            "diagnostics": hb_result.diagnostics,
            "warnings": warnings,
        }

    # ------------------------------------------------------------------
    # Pipeline steps
    # ------------------------------------------------------------------

    def _select_model(self, dataset: CBCRawDataset) -> str:
        """Auto-select statistical model based on data characteristics."""
        n_resp = dataset.metadata.n_respondents
        n_tasks = dataset.metadata.n_choice_sets

        if n_resp >= self.config.min_resp_for_hb and n_tasks >= self.config.min_tasks_per_resp:
            return "hb"
        return "mnl"

    def _fit_model(
        self,
        df_long: pd.DataFrame,
        feature_cols: list[str],
        model_type: str,
    ) -> HBResult:
        """Fit the selected model."""
        if model_type == "hb":
            config = HBConfig(
                n_draws=self.config.hb_draws,
                n_tune=self.config.hb_tune,
                n_chains=self.config.hb_chains,
                target_accept=self.config.hb_target_accept,
            )
            engine = HBEngine(config)
            return engine.fit(df_long, feature_cols)
        else:
            # MNL: fast aggregate-level baseline
            engine = MNLEngine()
            mnl_result = engine.fit(df_long, feature_cols)
            # Wrap MNLResult as HBResult for downstream compatibility
            return HBResult(
                converged=mnl_result.converged,
                rhat_max=1.0,  # MNL is deterministic
                ess_bulk_min=9999,  # Not applicable
                ess_tail_min=9999,
                population_mu=mnl_result.population_mu,
                population_sigma=mnl_result.population_sigma,
                individual_utilities=mnl_result.individual_utilities,
                diagnostics={
                    "rhat_max": 1.0,
                    "ess_bulk_min": 9999,
                    "converged": mnl_result.converged,
                    "reliable_ess": True,
                },
            )

    def _check_convergence(self, hb_result: HBResult) -> bool:
        """Check if MCMC has converged."""
        if hb_result.diagnostics is None:
            return False
        return (
            hb_result.diagnostics["rhat_max"] < self.config.rhat_threshold
            and hb_result.diagnostics["ess_bulk_min"] >= self.config.ess_min_threshold
        )

    def _check_price_coefficient(
        self,
        hb_result: HBResult,
        attributes: list[Attribute],
    ) -> list[str]:
        """Check if price coefficient has correct sign."""
        warnings: list[str] = []
        price_attrs = [a for a in attributes if a.type == AttributeType.PRICE]
        if not price_attrs:
            return warnings

        price_col = price_attrs[0].id
        if price_col not in hb_result.population_mu:
            return warnings

        mu_price = hb_result.population_mu[price_col]
        if mu_price > 0:
            warnings.append(
                f"价格系数为正 ({mu_price:.4f})，违背经济学直觉。建议检查数据编码或增加样本量。"
            )

        return warnings

    def _compute_wtp(
        self,
        util_df: pd.DataFrame,
        attributes: list[Attribute],
    ) -> tuple[WTPResponse | None, dict[str, float] | None]:
        """Compute WTP for all non-price attributes."""
        price_attrs = [a for a in attributes if a.type == AttributeType.PRICE]
        if not price_attrs:
            return None, None

        price_col = price_attrs[0].id
        if price_col not in util_df.columns:
            return None, None

        try:
            prices = [float(lv.value) for lv in price_attrs[0].levels]
            price_std = float(np.std(prices, ddof=0)) if len(prices) > 1 else 1.0
            wtp_calc = WTPCalculator(util_df, price_col=price_col, price_std=price_std)
            wtp_data = wtp_calc.compute_all_wtp(attributes)
            price_summary = wtp_calc.price_coefficient_summary()

            wtp_resp = WTPResponse(
                wtp_values={
                    attr_id: WTPAttribute(
                        comparisons=[
                            WTPComparison(
                                from_level=c["from_level"],
                                to_level=c["to_level"],
                                wtp_mean=c["wtp_mean"],
                                wtp_median=c["wtp_median"],
                                wtp_std=c["wtp_std"],
                                ci_95_lower=c["ci_95_lower"],
                                ci_95_upper=c["ci_95_upper"],
                                n_valid=c["n_valid"],
                            )
                            for c in attr_data["comparisons"]
                        ]
                    )
                    for attr_id, attr_data in wtp_data.items()
                },
                price_coefficient_summary=PriceCoefficientSummary(
                    mean=price_summary["mean"],
                    median=price_summary["median"],
                    std=price_summary["std"],
                    negative_rate=price_summary["negative_rate"],
                    n_positive_outliers=price_summary["n_positive_outliers"],
                ),
            )
            return wtp_resp, price_summary
        except Exception as exc:
            self._log.warning("wtp_computation_failed", error=str(exc))
            return None, None

    def _build_result(
        self,
        study_id: str,
        model_type: str,
        hb_result: HBResult,
        importance_agg: pd.DataFrame,
        wtp_resp: WTPResponse | None,
        price_summary: dict[str, float] | None,
        processing_time: float,
    ) -> AnalysisResultResponse:
        """Build the structured AnalysisResultResponse."""
        # Importance dict
        importance_dict = {
            attr_id: float(row["mean"]) for attr_id, row in importance_agg.iterrows()
        }

        # Convergence diagnostics
        diag = hb_result.diagnostics or {}
        convergence = ConvergenceDiagnostics(
            rhat_max=hb_result.rhat_max,
            rhat_by_param=diag.get("rhat_by_param", {}),
            ess_bulk_min=hb_result.ess_bulk_min,
            ess_tail_min=hb_result.ess_tail_min,
            ess_by_param=diag.get("ess_by_param", {}),
            converged=hb_result.converged,
            reliable_ess=diag.get("reliable_ess", False),
            divergences=diag.get("divergences", 0),
            tree_depth_max=diag.get("tree_depth_max", 0),
        )

        return AnalysisResultResponse(
            analysis_id=f"auto-{study_id}",
            study_id=study_id,
            status="COMPLETED",
            model_type=model_type,
            convergence=convergence,
            population_params={
                "mu": hb_result.population_mu,
                "sigma": hb_result.population_sigma,
            },
            individual_utilities=hb_result.individual_utilities,
            importance=importance_dict,
            wtp=wtp_resp.model_dump() if wtp_resp else {},
            processing_time_seconds=processing_time,
        )

    def _generate_report(
        self,
        result: AnalysisResultResponse,
        attributes: list[Attribute],
        warnings: list[str],
    ) -> AnalysisReport:
        """Generate natural-language interpretation."""
        findings: list[str] = []
        recommendations: list[str] = []

        # Convergence
        if result.convergence.converged:
            conv_text = (
                f"模型收敛良好 (R-hat max={result.convergence.rhat_max:.3f}, "
                f"ESS min={result.convergence.ess_bulk_min:.0f})"
            )
        else:
            conv_text = (
                f"模型未完全收敛 (R-hat max={result.convergence.rhat_max:.3f}). "
                f"建议增加采样次数或检查数据质量。"
            )
            recommendations.append("增加MCMC采样次数（n_draws ≥ 2000, n_tune ≥ 2000）")

        # Importance ranking
        sorted_importance = sorted(
            result.importance.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        top_attr = sorted_importance[0]
        findings.append(f"最重要的属性是'{top_attr[0]}'（重要性={top_attr[1]:.1%}）")

        if len(sorted_importance) > 1:
            second_attr = sorted_importance[1]
            findings.append(f"其次为'{second_attr[0]}'（重要性={second_attr[1]:.1%}）")

        # Price coefficient
        mu = (
            result.population_params.mu
            if hasattr(result.population_params, "mu")
            else result.population_params.get("mu", {})
        )
        price_attrs = [a for a in attributes if a.type == AttributeType.PRICE]
        if price_attrs and price_attrs[0].id in mu:
            price_coef = mu[price_attrs[0].id]
            if price_coef < 0:
                findings.append(f"价格系数为负 ({price_coef:.4f})，符合经济学直觉")
            else:
                findings.append(f"价格系数为正 ({price_coef:.4f})，需进一步检查")
                recommendations.append("检查价格属性编码和数据质量")

        # WTP summary
        if result.wtp:
            wtp_values = (
                result.wtp.wtp_values
                if hasattr(result.wtp, "wtp_values")
                else result.wtp.get("wtp_values", {})
            )
            if wtp_values:
                first_attr = list(wtp_values.keys())[0]
                comps = wtp_values[first_attr].get("comparisons", [])
                if comps:
                    findings.append(f"{first_attr}的WTP分析已完成，包含{len(comps)}个水平对比")

        # Summary
        summary = (
            f"联合分析完成（{result.model_type.upper()}模型）。"
            f"共{len(result.individual_utilities)}位受访者的个体效用已估计。"
            f"{conv_text}"
        )

        return AnalysisReport(
            summary=summary,
            key_findings=findings,
            convergence_assessment=conv_text,
            warnings=warnings,
            recommendations=recommendations,
        )
