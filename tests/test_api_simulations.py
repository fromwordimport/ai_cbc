"""Tests for behavior simulation API endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

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
from aicbc.core.store import get_store
from aicbc.main import app

client = TestClient(app)


def _make_test_persona(persona_id: str = "persona-simtest-001") -> PersonaProfile:
    """Build a test persona for simulation endpoints."""
    return PersonaProfile(
        persona_id=persona_id,
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


@pytest.fixture(autouse=True)
def _clean_store():
    """Clear the store before each test."""
    store = get_store()
    store._data.clear()
    yield
    store._data.clear()


class TestConverseEndpoint:
    """Tests for POST /personas/{id}/converse."""

    def test_converse_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A valid persona should return a conversational turn."""
        persona = _make_test_persona()
        get_store().save(persona)

        # Mock LLM to avoid real API calls
        def _mock_converse(*args, **kwargs):
            from aicbc.core.simulation.behavior_simulator import ConversationTurn
            return ConversationTurn(
                turn_number=1,
                researcher_question="测试问题",
                consumer_response="这是一个模拟回答。",
                emotion_tag="neutral",
                inconsistency_flag=False,
            )

        monkeypatch.setattr(
            "aicbc.core.simulation.behavior_simulator.BehaviorSimulator.converse",
            _mock_converse,
        )

        response = client.post(
            "/api/v1/personas/persona-simtest-001/converse",
            json={"question": "测试问题"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["persona_id"] == "persona-simtest-001"
        assert data["consumer_response"] == "这是一个模拟回答。"
        assert data["emotion_tag"] == "neutral"
        assert data["inconsistency_flag"] is False

    def test_converse_persona_not_found(self) -> None:
        """Non-existent persona should return 404."""
        response = client.post(
            "/api/v1/personas/persona-missing/converse",
            json={"question": "测试问题"},
        )
        assert response.status_code == 404


class TestInterviewEndpoint:
    """Tests for POST /personas/{id}/interview."""

    def test_interview_multiple_questions(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Multiple questions should produce multiple turns."""
        persona = _make_test_persona()
        get_store().save(persona)

        def _mock_interview(*args, **kwargs):
            from aicbc.core.simulation.behavior_simulator import ConversationTurn
            return [
                ConversationTurn(
                    turn_number=1,
                    researcher_question="问题1",
                    consumer_response="回答1",
                    emotion_tag="calm",
                ),
                ConversationTurn(
                    turn_number=2,
                    researcher_question="问题2",
                    consumer_response="回答2",
                    emotion_tag="excited",
                ),
            ]

        monkeypatch.setattr(
            "aicbc.core.simulation.behavior_simulator.BehaviorSimulator.run_interview",
            _mock_interview,
        )

        response = client.post(
            "/api/v1/personas/persona-simtest-001/interview",
            json={"questions": ["问题1", "问题2"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_turns"] == 2
        assert len(data["turns"]) == 2
        assert data["turns"][0]["turn_number"] == 1
        assert data["turns"][1]["emotion_tag"] == "excited"


class TestPurchaseDecisionEndpoint:
    """Tests for POST /personas/{id}/purchase-decision."""

    def test_purchase_decision_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A valid request should return a decision trace."""
        persona = _make_test_persona()
        get_store().save(persona)

        def _mock_purchase(*args, **kwargs):
            from aicbc.core.simulation.behavior_simulator import DecisionTrace
            return DecisionTrace(
                persona_id="persona-simtest-001",
                product_name="洗碗机X1",
                price_cny=4500.0,
                stages=[{"stage": "information_exposure", "interest_score": 0.7}],
                final_decision="buy",
                confidence=0.8,
            )

        monkeypatch.setattr(
            "aicbc.core.simulation.behavior_simulator.BehaviorSimulator.simulate_purchase_decision",
            _mock_purchase,
        )

        response = client.post(
            "/api/v1/personas/persona-simtest-001/purchase-decision",
            json={
                "product_name": "洗碗机X1",
                "price_cny": 4500.0,
                "core_selling_points": ["静音", "省水"],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["persona_id"] == "persona-simtest-001"
        assert data["final_decision"] == "buy"
        assert data["confidence"] == 0.8
        assert data["stage_count"] == 1

    def test_purchase_decision_persona_not_found(self) -> None:
        """Non-existent persona should return 404."""
        response = client.post(
            "/api/v1/personas/persona-missing/purchase-decision",
            json={
                "product_name": "测试产品",
                "price_cny": 3000.0,
            },
        )
        assert response.status_code == 404
