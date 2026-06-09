"""Pytest configuration and fixtures."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from aicbc.config.settings import Settings
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
from aicbc.core.store import PersonaStore
from aicbc.llm.client import LLMResponse, Provider

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@pytest.fixture
def test_settings() -> Settings:
    """Return test settings."""
    return Settings(environment="test", debug=True)


# ---------------------------------------------------------------------------
# Mock LLM helpers
# ---------------------------------------------------------------------------


def _mock_llm_response(content: dict[str, Any] | str, model: str = "claude-sonnet-4-6") -> LLMResponse:
    text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    return LLMResponse(
        content=text,
        model=model,
        provider=Provider.ANTHROPIC,
        prompt_tokens=100,
        completion_tokens=200,
        total_tokens=300,
        estimated_cost_usd=0.003,
        latency_seconds=0.5,
        raw_response=None,
    )


@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Return a mock LLMClient with layer response factory."""
    client = MagicMock()

    def _default_layer1() -> dict[str, Any]:
        return {
            "age": "28岁",
            "gender": "女",
            "city": "新一线",
            "income": "15-30万元",
            "occupation": "互联网产品经理",
            "education": "本科",
            "marital_status": "已婚无孩",
            "living_type": "自有住房（89㎡三居室）",
        }

    def _default_layer2() -> dict[str, Any]:
        return {
            "price_sensitivity": "对高频消费品价格敏感，对耐用品愿意为品质溢价",
            "purchase_channels": ["京东自营", "天猫旗舰店", "山姆会员店"],
            "decision_style": "参数党+口碑党混合，购买前必看测评",
            "brand_loyalty": "对信任品牌复购率高，愿意尝试新锐品牌",
            "information_source": ["小红书", "什么值得买", "知乎", "同事推荐"],
        }

    def _default_layer3() -> dict[str, Any]:
        return {
            "core_values": ["效率", "品质生活", "家庭至上"],
            "core_anxieties": ["时间不够用", "家务分工矛盾"],
            "tension_combination": {
                "labels": ["精致品质", "凑单退单高手"],
                "narrative_explanation": (
                    "她追求精致生活却总在凑单后退掉不需要的商品，这种矛盾源于她既想享受品质又害怕浪费金钱的深层焦虑。"
                    "小时候家境普通让她对浪费极度敏感，成年后收入提升让她有能力追求品质。"
                ),
            },
            "secret_motivation": "用科技产品证明自己的生活品味，缓解同辈压力",
            "defense_mechanism": "合理化——把冲动消费解释为投资生活品质",
        }

    def _default_layer4() -> dict[str, Any]:
        return {
            "daily_routine": "早7点起床，地铁通勤40分钟，晚7点到家，周末打扫或带孩子上兴趣班",
            "purchase_trigger": "被小红书提升幸福感的小家电种草，叠加同事推荐",
            "stress_response": "焦虑时刷购物APP加购，冷静后删除，形成加购-删除循环",
            "social_behavior": "朋友圈极少发消费内容，但在私域社群活跃分享购物攻略",
        }

    def _default_aux() -> dict[str, Any]:
        return {
            "language_samples": [
                "洗碗机真的是解放双手的神器，后悔没早买！",
                "对比了三个品牌，最后还是选了性价比最高的那款。",
                "安装师傅非常专业，只用了半小时就全部搞定了。",
            ],
            "dishwasher_context": {
                "purchase_constraints": ["厨房空间有限", "预算控制在5000以内"],
                "decision_factors": ["清洁效果", "品牌口碑", "能耗等级", "安装便利性"],
                "ignored_factors": ["外观设计", "智能互联功能"],
            },
        }

    def _side_effect(*args: Any, **kwargs: Any) -> LLMResponse:
        # Return responses in order: layer1, layer2, layer3, layer4, auxiliary
        if not hasattr(_side_effect, "call_count"):
            _side_effect.call_count = 0
        _side_effect.call_count += 1
        idx = (_side_effect.call_count - 1) % 5
        layers = [_default_layer1(), _default_layer2(), _default_layer3(), _default_layer4(), _default_aux()]
        return _mock_llm_response(layers[idx])

    client.generate.side_effect = _side_effect
    return client


# ---------------------------------------------------------------------------
# Clean store fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def clean_store() -> PersonaStore:
    """Return a fresh empty PersonaStore for each test."""
    store = PersonaStore()
    store.clear()
    return store


# ---------------------------------------------------------------------------
# Pre-built persona fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_persona() -> PersonaProfile:
    """Return a fully valid PersonaProfile for API testing."""
    return PersonaProfile(
        persona_id="persona-test-001",
        segment="初入职场单身-新一线城市",
        layer1_demographics=Layer1Demographics(
            age="28岁",
            gender="女",
            city="新一线",
            income="15-30万元",
            occupation="互联网产品经理",
            education="本科",
            marital_status="已婚无孩",
            living_type="自有住房（89㎡三居室）",
        ),
        layer2_behavior=Layer2Behavior(
            price_sensitivity="对高频消费品价格敏感，对耐用品愿意为品质溢价",
            purchase_channels=["京东自营", "天猫旗舰店", "山姆会员店"],
            decision_style="参数党+口碑党混合，购买前必看测评",
            brand_loyalty="对信任品牌复购率高，愿意尝试新锐品牌",
            information_source=["小红书", "什么值得买", "知乎", "同事推荐"],
        ),
        layer3_psychology=Layer3Psychology(
            core_values=["效率", "品质生活", "家庭至上"],
            core_anxieties=["时间不够用", "家务分工矛盾"],
            tension_combination=TensionCombination(
                labels=["精致品质", "凑单退单高手"],
                narrative_explanation=(
                    "她追求精致生活却总在凑单后退掉不需要的商品，这种矛盾源于她既想享受品质又害怕浪费金钱的深层焦虑。"
                    "小时候家境普通让她对浪费极度敏感，成年后收入提升让她有能力追求品质，但童年的匮乏感仍在潜意识中支配着她的消费决策。"
                ),
            ),
            secret_motivation="用科技产品证明自己的生活品味，缓解同辈压力",
            defense_mechanism="合理化——把冲动消费解释为投资生活品质",
        ),
        layer4_scenarios=Layer4Scenarios(
            daily_routine="早7点起床，地铁通勤40分钟，晚7点到家，周末打扫或带孩子上兴趣班",
            purchase_trigger="被小红书提升幸福感的小家电种草，叠加同事推荐",
            stress_response="焦虑时刷购物APP加购，冷静后删除，形成加购-删除循环",
            social_behavior="朋友圈极少发消费内容，但在私域社群活跃分享购物攻略",
        ),
        language_samples=[
            "洗碗机真的是解放双手的神器，后悔没早买！",
            "对比了三个品牌，最后还是选了性价比最高的那款。",
            "安装师傅非常专业，只用了半小时就全部搞定了。",
        ],
        dishwasher_context=DishwasherContext(
            purchase_constraints=["厨房空间有限", "预算控制在5000以内"],
            decision_factors=["清洁效果", "品牌口碑", "能耗等级", "安装便利性"],
            ignored_factors=["外观设计", "智能互联功能"],
        ),
        authenticity_score=11.0,
        bias_audit_status="PASSED",
        generation_metadata=GenerationMetadata(
            model="claude-sonnet-4-6",
            version="1.0",
            seed=42,
            cost_cny=2.5,
        ),
    )
