"""Tests for subsystem tools (generate_persona, create_study, simulate, analyze).

These tests verify that the three AI_CBC subsystems are correctly wrapped
as ToolCalling-compatible tools.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

from typing import Any

import pytest

# Import to trigger registration
import aicbc.tools.subsystems  # noqa: F401
from aicbc.tools.protocol import ToolCallStatus, call_tool

# ---------------------------------------------------------------------------
# Tool discovery
# ---------------------------------------------------------------------------


class TestToolDiscovery:
    def test_all_subsystem_tools_registered(self) -> None:
        from aicbc.tools.protocol import list_registered_tools

        tools = list_registered_tools()
        names = {t.name for t in tools}

        expected = {
            "generate_persona",
            "generate_persona_batch",
            "create_cbc_study",
            "generate_questionnaire",
            "simulate_cbc_choices",
            "run_conjoint_analysis",
            "batch_simulate_and_analyze",
        }
        assert expected.issubset(names), f"Missing tools: {expected - names}"

    def test_tool_specs_have_descriptions(self) -> None:
        from aicbc.tools.protocol import list_registered_tools

        for spec in list_registered_tools():
            if spec.name.startswith(("generate_", "create_", "simulate_", "run_", "batch_")):
                assert spec.description, f"Tool {spec.name} missing description"
                assert spec.timeout_seconds > 0, f"Tool {spec.name} missing timeout"


# ---------------------------------------------------------------------------
# create_cbc_study
# ---------------------------------------------------------------------------


class TestCreateCBCStudy:
    def test_create_study_default_attributes(self) -> None:
        result = call_tool(
            "create_cbc_study",
            study_id="test-dw-001",
            product_category="洗碗机",
            research_goal="测试研究",
        )

        assert result.is_success, f"Error: {result.error}"
        study = result.data
        assert study["study_id"] == "test-dw-001"
        assert study["product_category"] == "洗碗机"
        assert len(study["attributes"]) == 7  # Default dishwasher attributes
        assert study["design_parameters"]["n_choice_sets"] == 12
        assert study["design_parameters"]["n_alternatives"] == 3

    def test_create_study_custom_params(self) -> None:
        result = call_tool(
            "create_cbc_study",
            study_id="test-dw-002",
            product_category="洗碗机",
            research_goal="价格敏感度研究",
            n_choice_sets=8,
            n_alternatives=2,
            algorithm="balanced",
            target_segments=["精致白领", "Z世代租客"],
        )

        assert result.is_success
        study = result.data
        assert study["design_parameters"]["n_choice_sets"] == 8
        assert study["design_parameters"]["n_alternatives"] == 2
        assert study["design_parameters"]["algorithm"] == "balanced"
        assert study["target_segments"] == ["精致白领", "Z世代租客"]


# ---------------------------------------------------------------------------
# generate_questionnaire
# ---------------------------------------------------------------------------


class TestGenerateQuestionnaire:
    def test_generate_questionnaire(self) -> None:
        # First create a study
        study_result = call_tool(
            "create_cbc_study",
            study_id="test-q-001",
            product_category="洗碗机",
            research_goal="测试问卷生成",
            n_choice_sets=6,
            n_alternatives=3,
        )
        assert study_result.is_success
        study = study_result.data

        # Generate questionnaire
        result = call_tool(
            "generate_questionnaire",
            study=study,
            seed=42,
        )

        assert result.is_success, f"Error: {result.error}"
        q = result.data
        assert q["study_id"] == "test-q-001"
        assert len(q["choice_sets"]) == 6
        # Each choice set should have 3 alternatives
        for cs in q["choice_sets"]:
            assert len(cs["alternatives"]) == 3

    def test_generate_questionnaire_validation_error(self) -> None:
        # Pass invalid study dict
        result = call_tool(
            "generate_questionnaire",
            study={"invalid": "data"},
        )
        assert result.status == ToolCallStatus.ERROR


# ---------------------------------------------------------------------------
# simulate_cbc_choices
# ---------------------------------------------------------------------------


class TestSimulateCBCChoices:
    @pytest.fixture
    def sample_persona(self) -> dict[str, Any]:
        return {
            "persona_id": "persona-test-001",
            "segment": "精致白领",
            "layer1_demographics": {
                "age": "28岁",
                "gender": "女",
                "city": "新一线城市",
                "income": "月收入15K-25K",
                "occupation": "互联网运营",
                "education": "本科",
                "marital_status": "已婚无孩",
                "living_type": "70㎡两居室，租房",
            },
            "layer2_behavior": {
                "price_sensitivity": "中高敏感",
                "purchase_channels": ["京东", "天猫"],
                "decision_style": "理性比较型",
                "brand_loyalty": "中等，重性价比",
                "information_source": ["小红书", "知乎"],
            },
            "layer3_psychology": {
                "core_values": ["效率", "品质生活"],
                "core_anxieties": ["时间不够用"],
                "tension_combination": {
                    "labels": ["追求品质", "精打细算"],
                    "narrative_explanation": "她渴望通过高品质产品提升生活体验，但受限于租房身份和中等收入，必须在每一笔消费中权衡性价比，这让她常常陷入纠结。",
                },
                "secret_motivation": "用科技产品证明自己的生活品味",
                "defense_mechanism": "合理化：说服自己这是长期投资",
            },
            "layer4_scenarios": {
                "daily_routine": "早9晚7，周末打扫",
                "purchase_trigger": "看到同事晒洗碗机，心动",
                "stress_response": "焦虑时更容易冲动消费",
                "social_behavior": "爱在社交媒体分享好物",
            },
            "language_samples": [
                "洗碗机真的是解放双手的神器，后悔没早买啊。",
                "租房也要讲究生活品质，小厨房也能装洗碗机。",
                "对比了三款洗碗机，最后还是选了性价比最高的。",
            ],
            "dishwasher_context": {
                "purchase_constraints": ["厨房空间小", "租房不能大改"],
                "decision_factors": ["价格", "品牌口碑", "安装便捷性"],
                "ignored_factors": ["能耗等级", "智能功能"],
            },
            "authenticity_score": 11,
            "bias_audit_status": "PASSED",
        }

    @pytest.fixture
    def sample_questionnaire(self) -> dict[str, Any]:
        return {
            "questionnaire_id": "q-test-001",
            "study_id": "test-study-001",
            "attributes": [
                {
                    "id": "price",
                    "name": "价格",
                    "type": "price",
                    "levels": [
                        {"value": 2999, "label": "¥2,999"},
                        {"value": 3999, "label": "¥3,999"},
                        {"value": 4999, "label": "¥4,999"},
                        {"value": 5999, "label": "¥5,999"},
                    ],
                },
                {
                    "id": "brand",
                    "name": "品牌",
                    "type": "categorical",
                    "levels": [
                        {"value": "美的", "label": "美的"},
                        {"value": "西门子", "label": "西门子"},
                        {"value": "方太", "label": "方太"},
                        {"value": "小米", "label": "小米"},
                    ],
                },
            ],
            "choice_sets": [
                {
                    "choice_set_id": 1,
                    "alternatives": [
                        {"alt_index": 0, "attributes": {"price": 2999, "brand": "美的"}},
                        {"alt_index": 1, "attributes": {"price": 3999, "brand": "西门子"}},
                        {"alt_index": 2, "attributes": {"price": 4999, "brand": "方太"}},
                    ],
                },
                {
                    "choice_set_id": 2,
                    "alternatives": [
                        {"alt_index": 0, "attributes": {"price": 5999, "brand": "小米"}},
                        {"alt_index": 1, "attributes": {"price": 2999, "brand": "方太"}},
                        {"alt_index": 2, "attributes": {"price": 3999, "brand": "美的"}},
                    ],
                },
                {
                    "choice_set_id": 3,
                    "alternatives": [
                        {"alt_index": 0, "attributes": {"price": 4999, "brand": "西门子"}},
                        {"alt_index": 1, "attributes": {"price": 5999, "brand": "美的"}},
                        {"alt_index": 2, "attributes": {"price": 2999, "brand": "小米"}},
                    ],
                },
            ],
            "design_parameters": {
                "n_choice_sets": 3,
                "n_alternatives": 3,
                "algorithm": "d_optimal",
                "include_none": True,
            },
            "d_efficiency": 0.92,
        }

    def test_simulate_choices(
        self, sample_persona: dict[str, Any], sample_questionnaire: dict[str, Any]
    ) -> None:
        result = call_tool(
            "simulate_cbc_choices",
            persona=sample_persona,
            questionnaire=sample_questionnaire,
            seed=42,
        )

        assert result.is_success, f"Error: {result.error}"
        data = result.data

        # Check raw_dataset
        raw_dataset = data["raw_dataset"]
        assert "metadata" in raw_dataset
        assert "choice_records" in raw_dataset
        assert len(raw_dataset["choice_records"]) == 3  # 3 choice sets

        # Check persona_response
        response = data["persona_response"]
        assert response["persona_id"] == "persona-test-001"
        assert response["completion_status"] == "COMPLETED"
        assert len(response["responses"]) == 3

        # Each response should have a chosen alternative
        for r in response["responses"]:
            assert "chosen_alt_index" in r
            assert "reasoning" in r
            assert "confidence" in r

    def test_simulate_deterministic(
        self, sample_persona: dict[str, Any], sample_questionnaire: dict[str, Any]
    ) -> None:
        # With deterministic=True and same seed, should get same result
        result1 = call_tool(
            "simulate_cbc_choices",
            persona=sample_persona,
            questionnaire=sample_questionnaire,
            deterministic=True,
            seed=42,
        )
        result2 = call_tool(
            "simulate_cbc_choices",
            persona=sample_persona,
            questionnaire=sample_questionnaire,
            deterministic=True,
            seed=42,
        )

        assert result1.is_success and result2.is_success
        # In deterministic mode with same seed, choices should be identical
        r1_choices = [r["chosen_alt_index"] for r in result1.data["persona_response"]["responses"]]
        r2_choices = [r["chosen_alt_index"] for r in result2.data["persona_response"]["responses"]]
        assert r1_choices == r2_choices


# ---------------------------------------------------------------------------
# Integration: study -> questionnaire -> simulate
# ---------------------------------------------------------------------------


class TestIntegrationFlow:
    def test_full_flow_study_to_simulation(self) -> None:
        """Integration test: create study → generate questionnaire → simulate choices."""
        # Step 1: Create study
        study_result = call_tool(
            "create_cbc_study",
            study_id="integ-test-001",
            product_category="洗碗机",
            research_goal="集成测试",
            n_choice_sets=4,
            n_alternatives=3,
            seed=42,
        )
        assert study_result.is_success
        study = study_result.data

        # Step 2: Generate questionnaire
        q_result = call_tool(
            "generate_questionnaire",
            study=study,
            seed=42,
        )
        assert q_result.is_success
        questionnaire = q_result.data

        # Step 3: Create a simple persona
        persona = {
            "persona_id": "persona-integ-001",
            "segment": "测试群体",
            "layer1_demographics": {
                "age": "30岁",
                "gender": "男",
                "city": "一线城市",
                "income": "月收入20K",
                "occupation": "工程师",
                "education": "硕士",
                "marital_status": "已婚",
                "living_type": "90㎡三居室，自有",
            },
            "layer2_behavior": {
                "price_sensitivity": "中等敏感",
                "purchase_channels": ["京东"],
                "decision_style": "理性比较型",
                "brand_loyalty": "中等",
                "information_source": ["知乎"],
            },
            "layer3_psychology": {
                "core_values": ["效率"],
                "core_anxieties": ["时间不够用"],
                "tension_combination": {
                    "labels": ["追求效率", "拖延症"],
                    "narrative_explanation": "他渴望高效生活，但经常拖延，这种矛盾让他焦虑不已，每次拖延后都会自责，因此他总想用更智能的家电来减少日常决策负担。",
                },
                "secret_motivation": "证明自己",
                "defense_mechanism": "合理化",
            },
            "layer4_scenarios": {
                "daily_routine": "早8晚6",
                "purchase_trigger": "看到广告",
                "stress_response": "购物解压",
                "social_behavior": "低调",
            },
            "language_samples": [
                "洗碗机确实能省不少时间，亲朋好友来了我都强烈推荐大家购买。",
                "家里人口多，洗碗机是刚需电器，基本上每天都用得到。",
                "选洗碗机主要看容量和品牌口碑，千万别只图便宜。",
            ],
            "dishwasher_context": {
                "purchase_constraints": ["空间足够"],
                "decision_factors": ["价格", "品牌"],
                "ignored_factors": ["能耗"],
            },
            "authenticity_score": 10,
            "bias_audit_status": "PASSED",
        }

        # Step 4: Simulate
        sim_result = call_tool(
            "simulate_cbc_choices",
            persona=persona,
            questionnaire=questionnaire,
            seed=42,
        )
        assert sim_result.is_success, f"Simulation failed: {sim_result.error}"

        raw_dataset = sim_result.data["raw_dataset"]
        assert len(raw_dataset["choice_records"]) == 4  # 4 choice sets

        # Verify each record has correct structure
        for record in raw_dataset["choice_records"]:
            assert record["respondent_id"] == "persona-integ-001"
            assert len(record["alternatives"]) == 3
            # Exactly one alternative should be chosen
            chosen_count = sum(1 for a in record["alternatives"] if a["chosen"])
            assert chosen_count == 1, f"Expected 1 chosen, got {chosen_count}"
