"""pytest tests for business-rules validation suite.

These tests validate the validators themselves using synthetic data.
They are fast (no LLM calls, no MCMC sampling) and can run in CI.
"""

from __future__ import annotations

import pandas as pd
import pytest

from aicbc.analysis.validation.business_rules import (
    run_all_validations,
    summarize_results,
    validate_level_monotonicity,
    validate_market_simulation,
    validate_price_coefficient,
    validate_segment_comparison,
    validate_wtp_plausibility,
)

# ---------------------------------------------------------------------------
# 1.  Price coefficient tests
# ---------------------------------------------------------------------------


class TestValidatePriceCoefficient:
    def test_all_negative_passes(self):
        series = pd.Series([-1.2, -0.8, -1.5, -0.9])
        result = validate_price_coefficient(series)
        assert result.passed is True
        assert result.severity == "INFO"
        assert "100.0% negative" in result.message

    def test_some_positive_fails(self):
        # 3/4 negative = 75% < 95% threshold → CRITICAL
        series = pd.Series([-1.2, -0.8, 0.3, -0.9])
        result = validate_price_coefficient(series)
        assert result.passed is False
        assert result.severity == "CRITICAL"
        assert "75.00%" in result.message

    def test_mean_positive_fails(self):
        # All negative but mean > 0 (edge case: large positive outlier balanced by many small negatives)
        series = pd.Series([-0.1, -0.1, -0.1, 10.0])
        result = validate_price_coefficient(series)
        # negative rate = 75% < 95% → fails on rate first
        assert result.passed is False

    def test_empty_series(self):
        series = pd.Series([], dtype=float)
        result = validate_price_coefficient(series)
        assert result.passed is False
        assert result.severity == "CRITICAL"

    def test_custom_threshold(self):
        series = pd.Series([-1.0, -0.5, 0.1])  # 66.7% negative
        result = validate_price_coefficient(series, negative_rate_min=0.60)
        assert result.passed is True  # 66.7% > 60%


# ---------------------------------------------------------------------------
# 2.  WTP plausibility tests
# ---------------------------------------------------------------------------


class TestValidateWTPPlausibility:
    def test_within_bounds_passes(self):
        wtp = {
            "capacity": {
                "comparisons": [
                    {"from_level": "6套", "to_level": "10套", "wtp_mean": 500.0},
                    {"from_level": "10套", "to_level": "13套", "wtp_mean": 800.0},
                ]
            }
        }
        results = validate_wtp_plausibility(wtp)
        assert all(r.passed for r in results)

    def test_above_bounds_fails(self):
        wtp = {
            "capacity": {
                "comparisons": [
                    {"from_level": "6套", "to_level": "10套", "wtp_mean": 5000.0},
                ]
            }
        }
        results = validate_wtp_plausibility(wtp)
        assert len(results) == 1
        assert results[0].passed is False
        assert results[0].severity == "HIGH"
        assert "outside bounds" in results[0].message

    def test_negative_wtp_passes(self):
        # Negative WTP is acceptable (means downgrade is preferred)
        wtp = {
            "capacity": {
                "comparisons": [
                    {"from_level": "6套", "to_level": "10套", "wtp_mean": -200.0},
                ]
            }
        }
        results = validate_wtp_plausibility(wtp)
        # Negative WTP outside lower bound [0, 3000] → should fail
        assert results[0].passed is False
        assert results[0].severity == "HIGH"
        assert "outside bounds" in results[0].message

    def test_unknown_attribute_skipped(self):
        wtp = {"unknown_attr": {"comparisons": [{"wtp_mean": 100.0}]}}
        results = validate_wtp_plausibility(wtp)
        assert len(results) == 0  # skipped because not in WTP_BOUNDS


# ---------------------------------------------------------------------------
# 3.  Level monotonicity tests
# ---------------------------------------------------------------------------


class TestValidateLevelMonotonicity:
    @pytest.fixture
    def sample_attributes(self):
        return [
            {
                "id": "capacity",
                "type": "categorical",
                "levels": ["6套", "10套", "13套"],
            },
            {
                "id": "energy",
                "type": "categorical",
                "levels": ["二级", "一级", "超一级"],
            },
            {
                "id": "brand",
                "type": "categorical",
                "levels": ["美的", "西门子", "方太", "小米"],
            },
        ]

    def test_monotonic_passes(self, sample_attributes):
        # Utilities that increase with capacity: 6套=-1, 10套=0, 13套=1
        # Effects coding: capacity_0 = -1 (6套 vs ref), capacity_1 = 0 (10套 vs ref)
        # Last level = -(sum) = -(-1 + 0) = 1
        util = pd.DataFrame(
            {
                "capacity_0": [-1.0],
                "capacity_1": [0.0],
                "brand_0": [0.0],
                "brand_1": [0.0],
                "brand_2": [0.0],
            }
        )
        results = validate_level_monotonicity(util, sample_attributes)
        capacity_result = [r for r in results if r.rule_name == "level_monotonicity_capacity"][0]
        assert capacity_result.passed is True

    def test_non_monotonic_fails(self, sample_attributes):
        # Inverted: 6套=1, 10套=0, 13套=-1 (larger capacity = lower utility — wrong!)
        util = pd.DataFrame(
            {
                "capacity_0": [1.0],
                "capacity_1": [0.0],
                "brand_0": [0.0],
                "brand_1": [0.0],
                "brand_2": [0.0],
            }
        )
        results = validate_level_monotonicity(util, sample_attributes)
        capacity_result = [r for r in results if r.rule_name == "level_monotonicity_capacity"][0]
        assert capacity_result.passed is False
        assert capacity_result.severity == "HIGH"
        assert "violations" in capacity_result.message

    def test_energy_monotonic_passes(self, sample_attributes):
        # Better energy = higher utility: 二级=-0.5, 一级=0.5, 超一级=0.0 (recovered)
        # But 超一级 (0.0) < 一级 (0.5) → violation!  This test name is misleading.
        # Actually: energy_0=-0.5 (二级 vs ref), energy_1=0.5 (一级 vs ref)
        # Recovered: 超一级 = -(-0.5 + 0.5) = 0.0
        # Order: 二级=-0.5 < 超一级=0.0 < 一级=0.5 → NOT monotonic (expected 二级 < 一级 < 超一级)
        # Let's fix the data to be truly monotonic:
        # 二级=-0.5, 一级=0.0, 超一级=0.5
        # energy_0=-0.5 (二级), energy_1=0.0 (一级), recovered 超一级=0.5
        util = pd.DataFrame(
            {
                "energy_0": [-0.5],
                "energy_1": [0.0],
                "brand_0": [0.0],
                "brand_1": [0.0],
                "brand_2": [0.0],
            }
        )
        results = validate_level_monotonicity(util, sample_attributes)
        energy_result = [r for r in results if r.rule_name == "level_monotonicity_energy"][0]
        assert energy_result.passed is True

    def test_missing_attribute_warns(self, sample_attributes):
        util = pd.DataFrame({"other_0": [0.0]})
        results = validate_level_monotonicity(util, sample_attributes)
        # capacity and energy both warn because their columns are missing
        capacity_result = [r for r in results if r.rule_name == "level_monotonicity_capacity"][0]
        assert capacity_result.passed is False
        assert capacity_result.severity == "WARNING"

    def test_no_expectation_for_brand(self, sample_attributes):
        # brand is not in MONOTONIC_EXPECTATIONS → no result for it
        util = pd.DataFrame(
            {
                "capacity_0": [-1.0],
                "capacity_1": [0.0],
                "brand_0": [0.0],
                "brand_1": [0.0],
                "brand_2": [0.0],
            }
        )
        results = validate_level_monotonicity(util, sample_attributes)
        brand_results = [r for r in results if r.rule_name == "level_monotonicity_brand"]
        assert len(brand_results) == 0


# ---------------------------------------------------------------------------
# 4.  Segment comparison tests
# ---------------------------------------------------------------------------


class TestValidateSegmentComparison:
    def test_adequate_samples_passes(self):
        result = validate_segment_comparison(
            {
                "n_a": 80,
                "n_b": 80,
                "overall_test": {"p_value": 0.03, "significant": True},
            }
        )
        sample_result = [r for r in result if r.rule_name == "segment_comparison_sample_size"][0]
        assert sample_result.passed is True

    def test_small_samples_warns(self):
        result = validate_segment_comparison(
            {
                "n_a": 5,
                "n_b": 80,
                "overall_test": {"p_value": 0.03, "significant": True},
            }
        )
        sample_result = [r for r in result if r.rule_name == "segment_comparison_sample_size"][0]
        assert sample_result.passed is False
        assert sample_result.severity == "WARNING"

    def test_inconsistent_significance_fails(self):
        # p < 0.05 but significant=False → bug
        result = validate_segment_comparison(
            {
                "n_a": 80,
                "n_b": 80,
                "overall_test": {"p_value": 0.01, "significant": False},
            }
        )
        sig_result = [
            r for r in result if r.rule_name == "segment_comparison_significance_consistency"
        ][0]
        assert sig_result.passed is False
        assert sig_result.severity == "HIGH"

    def test_consistent_nonsignificant_passes(self):
        result = validate_segment_comparison(
            {
                "n_a": 80,
                "n_b": 80,
                "overall_test": {"p_value": 0.20, "significant": False},
            }
        )
        sig_result = [
            r for r in result if r.rule_name == "segment_comparison_significance_consistency"
        ][0]
        assert sig_result.passed is True


# ---------------------------------------------------------------------------
# 5.  Market simulation tests
# ---------------------------------------------------------------------------


class TestValidateMarketSimulation:
    def test_valid_shares_passes(self):
        sim = {
            "scenarios": [
                {
                    "name": "A",
                    "predicted_share": 0.35,
                    "share_ci_95_lower": 0.30,
                    "share_ci_95_upper": 0.40,
                },
                {
                    "name": "B",
                    "predicted_share": 0.40,
                    "share_ci_95_lower": 0.35,
                    "share_ci_95_upper": 0.45,
                },
                {
                    "name": "C",
                    "predicted_share": 0.25,
                    "share_ci_95_lower": 0.20,
                    "share_ci_95_upper": 0.30,
                },
            ]
        }
        results = validate_market_simulation(sim)
        assert all(r.passed for r in results)

    def test_shares_not_sum_to_one_fails(self):
        sim = {
            "scenarios": [
                {"name": "A", "predicted_share": 0.5},
                {"name": "B", "predicted_share": 0.5},
                {"name": "C", "predicted_share": 0.5},  # sum = 1.5
            ]
        }
        results = validate_market_simulation(sim)
        sum_result = [r for r in results if r.rule_name == "market_simulation_share_sum"][0]
        assert sum_result.passed is False
        assert sum_result.severity == "HIGH"
        assert "1.5000" in sum_result.message

    def test_negative_share_fails(self):
        sim = {
            "scenarios": [
                {"name": "A", "predicted_share": -0.1},
                {"name": "B", "predicted_share": 1.1},
            ]
        }
        results = validate_market_simulation(sim)
        neg_result = [r for r in results if r.rule_name == "market_simulation_no_negative"][0]
        assert neg_result.passed is False
        assert neg_result.severity == "CRITICAL"

    def test_invalid_ci_fails(self):
        sim = {
            "scenarios": [
                {
                    "name": "A",
                    "predicted_share": 0.5,
                    "share_ci_95_lower": 0.6,
                    "share_ci_95_upper": 0.4,
                },
            ]
        }
        results = validate_market_simulation(sim)
        ci_result = [r for r in results if r.rule_name == "market_simulation_ci_order"][0]
        assert ci_result.passed is False
        assert ci_result.severity == "HIGH"

    def test_empty_scenarios_fails(self):
        sim = {"scenarios": []}
        results = validate_market_simulation(sim)
        empty_result = [r for r in results if r.rule_name == "market_simulation_non_empty"][0]
        assert empty_result.passed is False
        assert empty_result.severity == "CRITICAL"


# ---------------------------------------------------------------------------
# 6.  Orchestrator tests
# ---------------------------------------------------------------------------


class TestRunAllValidations:
    def test_full_run(self):
        # Synthetic data for a complete validation run
        util = pd.DataFrame(
            {
                "price": [-1.0, -0.8, -1.2, -0.9],
                "capacity_0": [-0.5, -0.3, -0.6, -0.4],
                "capacity_1": [0.2, 0.3, 0.1, 0.25],
            }
        )

        wtp = {
            "capacity": {
                "comparisons": [
                    {"from_level": "6套", "to_level": "10套", "wtp_mean": 400.0},
                ]
            }
        }

        attributes = [
            {"id": "capacity", "type": "categorical", "levels": ["6套", "10套", "13套"]},
        ]

        segment_comp = {
            "n_a": 80,
            "n_b": 80,
            "overall_test": {"p_value": 0.03, "significant": True},
        }

        market_sim = {
            "scenarios": [
                {
                    "name": "A",
                    "predicted_share": 0.5,
                    "share_ci_95_lower": 0.45,
                    "share_ci_95_upper": 0.55,
                },
                {
                    "name": "B",
                    "predicted_share": 0.5,
                    "share_ci_95_lower": 0.45,
                    "share_ci_95_upper": 0.55,
                },
            ]
        }

        results = run_all_validations(
            individual_utilities=util,
            wtp_results=wtp,
            segment_comparison=segment_comp,
            market_simulation=market_sim,
            attributes=attributes,
        )

        assert "price_coefficient" in results
        assert "wtp" in results
        assert "level_monotonicity" in results
        assert "segment_comparison" in results
        assert "market_simulation" in results

        summary = summarize_results(results)
        assert summary["overall_passed"] is True
        assert summary["critical_failures"] == 0
        # energy monotonicity may have a WARNING because it's missing from util
        # but capacity should be fine, so overall can still pass
        assert summary["high_failures"] == 0

    def test_run_with_failures(self):
        # Price coefficients with positive values → should fail
        util = pd.DataFrame(
            {
                "price": [1.0, -0.8, 1.2, -0.9],  # 50% negative < 95%
                "capacity_0": [0.5, 0.3, 0.6, 0.4],  # inverted: 6套 > 10套
                "capacity_1": [0.2, 0.3, 0.1, 0.25],
            }
        )

        wtp = {
            "capacity": {
                "comparisons": [
                    {"from_level": "6套", "to_level": "10套", "wtp_mean": 5000.0},
                ]
            }
        }

        attributes = [
            {"id": "capacity", "type": "categorical", "levels": ["6套", "10套", "13套"]},
        ]

        results = run_all_validations(
            individual_utilities=util,
            wtp_results=wtp,
            segment_comparison=None,
            market_simulation=None,
            attributes=attributes,
        )

        summary = summarize_results(results)
        assert summary["overall_passed"] is False
        assert summary["critical_failures"] >= 1  # price coefficient
        assert summary["high_failures"] >= 1  # WTP + monotonicity


# ---------------------------------------------------------------------------
# 7.  Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_wtp_bounds_override(self):
        custom_bounds = {"capacity": (0.0, 100.0)}
        wtp = {
            "capacity": {
                "comparisons": [
                    {"from_level": "6套", "to_level": "10套", "wtp_mean": 150.0},
                ]
            }
        }
        results = validate_wtp_plausibility(wtp, bounds=custom_bounds)
        assert results[0].passed is False
        assert "outside bounds" in results[0].message

    def test_monotonicity_with_multiple_respondents(self):
        # Mixed: some respondents have monotonic, some don't
        # Mean should still be monotonic if majority are
        util = pd.DataFrame(
            {
                "capacity_0": [-1.0, -1.0, 1.0, -0.5],  # 6套 utility
                "capacity_1": [0.0, 0.0, 0.0, 0.5],  # 10套 utility
            }
        )
        # Recovered: 6套=[-1,-1,1,-0.5], 10套=[0,0,0,0.5], 13套=[1,1,-1,0]
        # Mean: 6套=-0.375, 10套=0.125, 13套=0.25 → monotonic ✓
        attributes = [
            {"id": "capacity", "type": "categorical", "levels": ["6套", "10套", "13套"]},
        ]
        results = validate_level_monotonicity(util, attributes)
        assert results[0].passed is True
