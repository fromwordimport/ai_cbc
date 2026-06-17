"""Tests for aicbc.llm.router."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from aicbc.llm.router import BudgetStatus, ModelRouter, TaskType


@pytest.fixture
def router() -> ModelRouter:
    return ModelRouter()


class TestBudgetStatusUpdate:
    def test_normal_status(self, router: ModelRouter) -> None:
        status = router.update_budget_status(100.0, budget=1000.0)
        assert status == BudgetStatus.NORMAL
        assert router.get_budget_status() == BudgetStatus.NORMAL

    def test_warning_status(self, router: ModelRouter) -> None:
        status = router.update_budget_status(850.0, budget=1000.0)
        assert status == BudgetStatus.WARNING

    def test_degrade_status(self, router: ModelRouter) -> None:
        status = router.update_budget_status(950.0, budget=1000.0)
        assert status == BudgetStatus.DEGRADE

    def test_fuse_status(self, router: ModelRouter) -> None:
        status = router.update_budget_status(1000.0, budget=1000.0)
        assert status == BudgetStatus.FUSE

    def test_emergency_status(self, router: ModelRouter) -> None:
        status = router.update_budget_status(1200.0, budget=1000.0)
        assert status == BudgetStatus.EMERGENCY

    def test_zero_budget_defaults_to_normal(self, router: ModelRouter) -> None:
        status = router.update_budget_status(100.0, budget=0.0)
        assert status == BudgetStatus.NORMAL

    def test_status_change_logged_only_once(self, router: ModelRouter) -> None:
        with (
            patch.object(router, "_current_budget_status", BudgetStatus.NORMAL),
            patch("aicbc.llm.router.logger.warning") as mock_warning,
        ):
            router.update_budget_status(850.0, budget=1000.0)
            assert mock_warning.called
            mock_warning.reset_mock()
            router.update_budget_status(860.0, budget=1000.0)
            assert not mock_warning.called


class TestRoute:
    def test_route_uses_preferred_model_when_enabled(self, router: ModelRouter) -> None:
        with patch("aicbc.llm.router.CostFuse") as mock_fuse_cls:
            mock_fuse_cls.return_value.pre_call_check.return_value = (True, "normal", "")
            model = router.route({"type": TaskType.PERSONA_GENERATION, "preferred_model": "gpt-4o"})
            assert model == "gpt-4o"

    def test_route_falls_back_when_preferred_disabled(self, router: ModelRouter) -> None:
        router.models["gpt-4o"].enabled = False
        with patch("aicbc.llm.router.CostFuse") as mock_fuse_cls:
            mock_fuse_cls.return_value.pre_call_check.return_value = (True, "normal", "")
            model = router.route({"type": TaskType.PERSONA_GENERATION, "preferred_model": "gpt-4o"})
            assert model == "claude-sonnet-4-6"

    def test_route_normal_budget(self, router: ModelRouter) -> None:
        with patch("aicbc.llm.router.CostFuse") as mock_fuse_cls:
            mock_fuse_cls.return_value.pre_call_check.return_value = (True, "normal", "")
            model = router.route({"type": TaskType.PERSONA_GENERATION})
            assert model == "claude-sonnet-4-6"

    def test_route_degrade_budget(self, router: ModelRouter) -> None:
        with patch("aicbc.llm.router.CostFuse") as mock_fuse_cls:
            mock_fuse_cls.return_value.pre_call_check.return_value = (
                True,
                "degrade",
                "claude-haiku-4-5",
            )
            model = router.route({"type": TaskType.PERSONA_GENERATION})
            assert model == "claude-haiku-4-5"

    def test_route_degrade_uses_fallback_when_degrade_unavailable(
        self, router: ModelRouter
    ) -> None:
        router.models["claude-haiku-4-5"].enabled = False
        with patch("aicbc.llm.router.CostFuse") as mock_fuse_cls:
            mock_fuse_cls.return_value.pre_call_check.return_value = (
                True,
                "degrade",
                "claude-haiku-4-5",
            )
            model = router.route({"type": TaskType.PERSONA_GENERATION})
            assert model == "gpt-4o"

    def test_route_degrade_returns_default_when_no_fallback(self, router: ModelRouter) -> None:
        router.models["claude-haiku-4-5"].enabled = False
        router.models["gpt-4o"].enabled = False
        with patch("aicbc.llm.router.CostFuse") as mock_fuse_cls:
            mock_fuse_cls.return_value.pre_call_check.return_value = (
                True,
                "degrade",
                "claude-haiku-4-5",
            )
            model = router.route({"type": TaskType.PERSONA_GENERATION})
            assert model == "claude-sonnet-4-6"

    def test_route_warning_with_low_complexity_uses_degrade(self, router: ModelRouter) -> None:
        with patch("aicbc.llm.router.CostFuse") as mock_fuse_cls:
            mock_fuse_cls.return_value.pre_call_check.return_value = (True, "warning", "")
            model = router.route({"type": TaskType.PERSONA_GENERATION, "complexity": "low"})
            assert model == "claude-haiku-4-5"

    def test_route_warning_with_low_urgency_uses_degrade(self, router: ModelRouter) -> None:
        with patch("aicbc.llm.router.CostFuse") as mock_fuse_cls:
            mock_fuse_cls.return_value.pre_call_check.return_value = (True, "warning", "")
            model = router.route({"type": TaskType.PERSONA_GENERATION, "urgency": "low"})
            assert model == "claude-haiku-4-5"

    def test_route_warning_high_priority_uses_default(self, router: ModelRouter) -> None:
        with patch("aicbc.llm.router.CostFuse") as mock_fuse_cls:
            mock_fuse_cls.return_value.pre_call_check.return_value = (True, "warning", "")
            model = router.route(
                {"type": TaskType.PERSONA_GENERATION, "complexity": "high", "urgency": "high"}
            )
            assert model == "claude-sonnet-4-6"

    def test_route_fuse_budget_raises(self, router: ModelRouter) -> None:
        with patch("aicbc.llm.router.CostFuse") as mock_fuse_cls:
            mock_fuse_cls.return_value.pre_call_check.return_value = (False, "fuse", "")
            with pytest.raises(RuntimeError, match="fuse"):
                router.route({"type": TaskType.PERSONA_GENERATION})

    def test_route_emergency_budget_raises(self, router: ModelRouter) -> None:
        with patch("aicbc.llm.router.CostFuse") as mock_fuse_cls:
            mock_fuse_cls.return_value.pre_call_check.return_value = (False, "emergency", "")
            with pytest.raises(RuntimeError, match="emergency"):
                router.route({"type": TaskType.PERSONA_GENERATION})

    def test_route_unknown_task_type_uses_default(self, router: ModelRouter) -> None:
        with patch("aicbc.llm.router.CostFuse") as mock_fuse_cls:
            mock_fuse_cls.return_value.pre_call_check.return_value = (True, "normal", "")
            model = router.route({"type": "unknown_task"})
            assert model == "claude-sonnet-4-6"

    def test_route_default_disabled_falls_back(self, router: ModelRouter) -> None:
        router.models["claude-sonnet-4-6"].enabled = False
        with patch("aicbc.llm.router.CostFuse") as mock_fuse_cls:
            mock_fuse_cls.return_value.pre_call_check.return_value = (True, "normal", "")
            model = router.route({"type": TaskType.DEFAULT})
            assert model == "claude-haiku-4-5"

    def test_route_all_defaults_disabled_raises(self, router: ModelRouter) -> None:
        for model in router.models.values():
            model.enabled = False
        with patch("aicbc.llm.router.CostFuse") as mock_fuse_cls:
            mock_fuse_cls.return_value.pre_call_check.return_value = (True, "normal", "")
            with pytest.raises(RuntimeError, match="No available model"):
                router.route({"type": TaskType.DEFAULT})


class TestModelInfo:
    def test_get_model_info_for_single_model(self, router: ModelRouter) -> None:
        info = router.get_model_info("gpt-4o")
        assert info["name"] == "gpt-4o"
        assert info["provider"] == "openai"

    def test_get_model_info_unknown_returns_empty(self, router: ModelRouter) -> None:
        assert router.get_model_info("unknown") == {}

    def test_get_model_info_all_models(self, router: ModelRouter) -> None:
        info = router.get_model_info()
        assert "gpt-4o" in info
        assert "claude-sonnet-4-6" in info


class TestFailureHandling:
    def test_record_failure(self, router: ModelRouter) -> None:
        router.record_failure("gpt-4o")
        assert router.models["gpt-4o"].failure_count == 1
        assert router.models["gpt-4o"].last_failure is not None

    def test_record_failure_disables_after_ten(self, router: ModelRouter) -> None:
        for _ in range(10):
            router.record_failure("gpt-4o-mini")
        assert not router.models["gpt-4o-mini"].enabled

    def test_record_failure_unknown_model_is_noop(self, router: ModelRouter) -> None:
        router.record_failure("unknown")


class TestSwitchModel:
    def test_switch_model_updates_all_routes(self, router: ModelRouter) -> None:
        router.switch_model("gpt-4o", "test")
        for rule in router.routes.values():
            assert rule.default_model == "gpt-4o"

    def test_switch_unknown_model_raises(self, router: ModelRouter) -> None:
        with pytest.raises(ValueError, match="Unknown model"):
            router.switch_model("unknown", "test")


class TestRoutingSummary:
    def test_summary_contains_budget_and_models(self, router: ModelRouter) -> None:
        router.update_budget_status(500.0, budget=1000.0)
        summary = router.get_routing_summary()
        assert summary["budget_status"] == "normal"
        assert summary["current_daily_cost"] == 500.0
        assert "models" in summary
        assert "routes" in summary


class TestLoadConfig:
    def test_load_json_config(self, router: ModelRouter, tmp_path: Path) -> None:
        config_path = tmp_path / "config.json"
        config_path.write_text(
            '{"models": {"test-model": {"provider": "test", "input_cost_per_1k": 1.0, "output_cost_per_1k": 2.0, "max_tokens": 1000, "quality_tier": "low"}}}'
        )
        router._load_config(str(config_path))
        assert "test-model" in router.models

    def test_load_yaml_config(self, router: ModelRouter, tmp_path: Path) -> None:
        config_path = tmp_path / "config.yaml"
        data = {
            "models": {
                "yaml-model": {
                    "provider": "test",
                    "input_cost_per_1k": 1.0,
                    "output_cost_per_1k": 2.0,
                    "max_tokens": 1000,
                    "quality_tier": "low",
                }
            }
        }
        config_path.write_text(yaml.safe_dump(data))
        router._load_config(str(config_path))
        assert "yaml-model" in router.models

    def test_load_missing_config_is_noop(self, router: ModelRouter) -> None:
        router._load_config("/nonexistent/path.json")

    def test_load_invalid_config_logs_warning(self, router: ModelRouter, tmp_path: Path) -> None:
        config_path = tmp_path / "bad.json"
        config_path.write_text("not json")
        router._load_config(str(config_path))
