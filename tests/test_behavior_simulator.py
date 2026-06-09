"""Tests for BehaviorSimulator (conversation and purchase-decision modes)."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from aicbc.core.models.persona import (
    DishwasherContext,
    GenerationMetadata,
    Layer1Demographics,
    Layer2Behavior,
    Layer3Psychology,
    Layer4Scenarios,
    PersonaProfile,
    TensionCombination,
)
from aicbc.core.simulation.behavior_simulator import BehaviorSimulator
from aicbc.llm.client import LLMResponse, Provider


def _mock_llm_response(content: dict[str, Any], model: str = "claude-sonnet-4-6") -> LLMResponse:
    text = json.dumps(content, ensure_ascii=False)
    return LLMResponse(
        content=text, model=model, provider=Provider.ANTHROPIC,
        prompt_tokens=100, completion_tokens=200, total_tokens=300,
        estimated_cost_usd=0.003, latency_seconds=0.5, raw_response=None,
    )


@pytest.fixture
def sample_persona() -> PersonaProfile:
    """Return a fully populated persona for simulation tests."""
    return PersonaProfile(
        persona_id="persona-sim-001",
        segment="精致白领-新一线城市",
        layer1_demographics=Layer1Demographics(
            age="28岁", gender="女", city="新一线城市", income="15-30万元",
            occupation="互联网产品经理", education="本科",
            marital_status="已婚无孩", living_type="自有住房（89㎡）",
        ),
        layer2_behavior=Layer2Behavior(
            price_sensitivity="中等敏感",
            purchase_channels=["京东", "天猫"],
            decision_style="理性比较型",
            brand_loyalty="中等",
            information_source=["小红书", "知乎"],
        ),
        layer3_psychology=Layer3Psychology(
            core_values=["效率", "品质"],
            core_anxieties=["时间不够"],
            tension_combination=TensionCombination(
                labels=["精致品质", "凑单退单"],
                narrative_explanation="她追求精致生活却总在凑单后退掉不需要的商品，这种矛盾源于她既想享受品质又害怕浪费金钱的深层焦虑，这是她内心最真实的状态。",
            ),
            secret_motivation="用科技产品证明品味",
            defense_mechanism="合理化——把消费解释为投资",
        ),
        layer4_scenarios=Layer4Scenarios(
            daily_routine="早7点起床，通勤40分钟，晚7点到家",
            purchase_trigger="被小红书种草",
            stress_response="焦虑时刷购物APP",
            social_behavior="朋友圈少发，私域活跃",
        ),
        language_samples=[
            "洗碗机用起来真的很方便，洗完的碗都亮晶晶的。",
            "对比了好几个品牌，最后还是选了这个性价比高的。",
            "安装师傅非常专业，只用了半小时就全部搞定了。",
        ],
        dishwasher_context=DishwasherContext(
            purchase_constraints=["厨房小"],
            decision_factors=["价格", "品牌"],
            ignored_factors=["外观"],
        ),
        generation_metadata=GenerationMetadata(),
    )


@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Return a mock LLMClient with conversation response."""
    client = MagicMock()
    client.generate_json.return_value = {
        "response": "最近确实在看洗碗机，但是有点纠结，怕买了之后家里老人不会用。",
        "emotion": "hesitant",
        "inconsistency_warning": False,
    }
    return client


# ---------------------------------------------------------------------------
# Mode A: Conversation
# ---------------------------------------------------------------------------


class TestConversationMode:
    """Tests for conversational research simulation."""

    def test_converse_returns_turn(self, mock_llm_client: MagicMock, sample_persona: PersonaProfile) -> None:
        """A single conversational turn should return structured output."""
        sim = BehaviorSimulator(llm_client=mock_llm_client)
        turn = sim.converse(
            persona=sample_persona,
            researcher_question="你最近有买过什么让自己开心或后悔的东西吗？",
        )

        assert turn.turn_number == 1
        assert turn.researcher_question == "你最近有买过什么让自己开心或后悔的东西吗？"
        assert "纠结" in turn.consumer_response or "洗碗机" in turn.consumer_response
        assert turn.emotion_tag == "hesitant"
        assert turn.inconsistency_flag is False

    def test_converse_uses_context(self, mock_llm_client: MagicMock, sample_persona: PersonaProfile) -> None:
        """Context should be passed to the LLM prompt."""
        sim = BehaviorSimulator(llm_client=mock_llm_client)
        sim.converse(
            persona=sample_persona,
            researcher_question="测试问题",
            context={"时间": "周末下午", "情绪": "疲惫"},
        )

        call_args = mock_llm_client.generate_json.call_args
        messages = call_args.kwargs["messages"]
        prompt = messages[1]["content"]  # user message
        assert "周末下午" in prompt
        assert "疲惫" in prompt

    def test_converse_failure_graceful(self, sample_persona: PersonaProfile) -> None:
        """LLM failure should return a fallback turn, not crash."""
        failing_client = MagicMock()
        failing_client.generate_json.side_effect = RuntimeError("API down")

        sim = BehaviorSimulator(llm_client=failing_client)
        turn = sim.converse(
            persona=sample_persona,
            researcher_question="任何问题",
        )

        assert turn.consumer_response == "[模拟生成失败]"
        assert turn.emotion_tag == "unknown"

    def test_run_interview_multiple_questions(self, mock_llm_client: MagicMock, sample_persona: PersonaProfile) -> None:
        """Running an interview with multiple questions should produce multiple turns."""
        sim = BehaviorSimulator(llm_client=mock_llm_client)
        questions = [
            "最近有买过什么让自己开心的东西吗？",
            "如果朋友问你这个值不值，你会怎么说？",
            "你有没有过'明知道不该买但还是买了'的时候？",
        ]
        turns = sim.run_interview(sample_persona, questions)

        assert len(turns) == 3
        assert turns[0].turn_number == 1
        assert turns[1].turn_number == 2
        assert turns[2].turn_number == 3


# ---------------------------------------------------------------------------
# Mode B: Purchase decision
# ---------------------------------------------------------------------------


class TestPurchaseDecisionMode:
    """Tests for purchase-decision simulation."""

    def test_simulate_purchase_low_interest(self, sample_persona: PersonaProfile) -> None:
        """If stage 1 shows low interest, simulation should short-circuit."""
        client = MagicMock()
        client.generate_json.return_value = {
            "first_notice": "价格",
            "initial_emotion": "bored",
            "three_second_judgment": "不买",
            "interest_score": 0.1,
            "internal_dialogue": "太贵了，不考虑",
        }

        sim = BehaviorSimulator(llm_client=client)
        trace = sim.simulate_purchase_decision(
            persona=sample_persona,
            product={"name": "高端洗碗机", "price_cny": 15000, "core_selling_points": ["智能", "静音"]},
        )

        assert trace.final_decision == "not_buy"
        assert trace.confidence >= 0.5
        assert len(trace.stages) == 1  # Only stage 1 ran

    def test_simulate_purchase_full_flow(self, sample_persona: PersonaProfile) -> None:
        """High interest should trigger all 3 stages."""
        call_count = 0

        def _stage_side_effect(*args: Any, **kwargs: Any) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "first_notice": "外观",
                    "initial_emotion": "curious",
                    "three_second_judgment": "再看看",
                    "interest_score": 0.7,
                    "internal_dialogue": "挺好看的，看看价格",
                }
            elif call_count == 2:
                return {
                    "questions_asked": ["耗电吗？", "噪音大吗？"],
                    "search_terms": ["洗碗机测评"],
                    "will_check_reviews": True,
                    "will_compare_prices": True,
                    "concerns": ["价格偏高"],
                    "excitement_triggers": ["颜值高"],
                }
            else:
                return {
                    "decision": "buy",
                    "confidence": 0.8,
                    "decision_speed_change": "加速",
                    "typical_behaviors": ["凑单", "询问客服"],
                    "emotion_shift": "从犹豫到兴奋",
                    "rationalization": "反正迟早要买，趁促销入手",
                }

        client = MagicMock()
        client.generate_json.side_effect = _stage_side_effect

        sim = BehaviorSimulator(llm_client=client)
        trace = sim.simulate_purchase_decision(
            persona=sample_persona,
            product={"name": "洗碗机X1", "price_cny": 4500, "core_selling_points": ["静音", "省水"]},
        )

        assert trace.final_decision == "buy"
        assert trace.confidence == 0.8
        assert len(trace.stages) == 3
        assert trace.stages[0]["stage"] == "information_exposure"
        assert trace.stages[1]["stage"] == "active_exploration"
        assert trace.stages[2]["stage"] == "decision_pressure"

    def test_stage_fallback_on_failure(self, sample_persona: PersonaProfile) -> None:
        """Individual stage failure should use fallback, not abort entire trace."""
        client = MagicMock()
        client.generate_json.side_effect = RuntimeError("API error")

        sim = BehaviorSimulator(llm_client=client)
        trace = sim.simulate_purchase_decision(
            persona=sample_persona,
            product={"name": "测试产品", "price_cny": 3000, "core_selling_points": ["便宜"]},
        )

        # Should still produce a trace with fallback values
        assert trace.persona_id == "persona-sim-001"
        assert trace.product_name == "测试产品"
        assert len(trace.stages) >= 1
