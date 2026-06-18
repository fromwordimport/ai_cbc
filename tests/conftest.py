"""Pytest configuration and fixtures."""

from __future__ import annotations

# Force debug mode for the test suite so that API-key enforcement is skipped and
# RBAC defaults to admin. Auth/authorization is exercised separately in
# tests/unit/security and tests/redteam.
import os

os.environ.setdefault("DEBUG", "true")

import json
from collections.abc import AsyncGenerator, Generator
from contextlib import suppress
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from aicbc.config.settings import Settings, get_settings
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
from aicbc.core.store import PersonaStore, areset_stores
from aicbc.cost.tracker import _REDIS_KEY, reset_cost_tracker
from aicbc.llm.client import LLMResponse, Provider

# ---------------------------------------------------------------------------
# Session-level state cleanup
# ---------------------------------------------------------------------------

_COST_STATE_FILE = Path("./data/cost_state.json")


def _delete_cost_state_file() -> None:
    """Delete the on-disk cost state file, ignoring errors."""
    try:
        if _COST_STATE_FILE.exists():
            _COST_STATE_FILE.unlink()
    except Exception:
        pass


def _delete_cost_state_redis() -> None:
    """Delete the Redis cost state key, ignoring errors."""
    try:
        from aicbc.config.settings import get_settings

        settings = get_settings()
        if settings.cost_tracker.backend == "redis":
            import redis

            r = redis.Redis.from_url(settings.database.redis_url, decode_responses=True)
            r.delete(_REDIS_KEY)
    except Exception:
        pass


@pytest.fixture(scope="session", autouse=True)
def _clean_cost_state_on_disk() -> Generator[None, None, None]:
    """Delete persisted cost state before any tests run.

    This prevents stale cost data from previous test runs from leaking into
    CostTracker instances that call _load_state() in __init__.
    """
    _delete_cost_state_file()
    _delete_cost_state_redis()
    yield
    # Clean up after session as well
    _delete_cost_state_file()
    _delete_cost_state_redis()


# ---------------------------------------------------------------------------
# Per-function state cleanup (autouse)
# ---------------------------------------------------------------------------

# Lazy imports for modules that pull in heavy deps (pandas, prometheus_client).
# These are resolved once and cached so the fixture body avoids re-importing
# them on every test function.
_reset_dependencies_fn = None
_reset_analysis_store_fn = None
_app_obj = None  # FastAPI app — only loaded for tests that need it
_reset_rate_limits_fn = None


def _lazy_reset_dependencies() -> None:
    global _reset_dependencies_fn
    if _reset_dependencies_fn is None:
        from aicbc.api.dependencies import reset_dependencies as fn

        _reset_dependencies_fn = fn
    _reset_dependencies_fn()


async def _lazy_areset_analysis_store() -> None:
    global _reset_analysis_store_fn
    if _reset_analysis_store_fn is None:
        from aicbc.analysis.store import areset_analysis_store as fn

        _reset_analysis_store_fn = fn
    await _reset_analysis_store_fn()


def _lazy_clear_app_overrides() -> None:
    global _app_obj
    if _app_obj is None:
        from aicbc.main import app as _app

        _app_obj = _app
    _app_obj.dependency_overrides.clear()


def _lazy_reset_rate_limits() -> None:
    global _reset_rate_limits_fn
    if _reset_rate_limits_fn is None:
        from aicbc.api.middleware.rate_limit import reset_rate_limits as fn

        _reset_rate_limits_fn = fn
    _reset_rate_limits_fn()


async def _reset_all() -> None:
    """Reset all global singletons and persisted state, suppressing errors."""
    with suppress(Exception):
        _lazy_reset_dependencies()
    with suppress(Exception):
        get_settings.cache_clear()
    with suppress(Exception):
        await areset_stores()
    with suppress(Exception):
        await _lazy_areset_analysis_store()
    with suppress(Exception):
        reset_cost_tracker()
    with suppress(Exception):
        _lazy_clear_app_overrides()
    with suppress(Exception):
        _lazy_reset_rate_limits()
    with suppress(Exception):
        _delete_cost_state_file()
    with suppress(Exception):
        _delete_cost_state_redis()


@pytest.fixture(autouse=True)
async def _clean_global_state() -> AsyncGenerator[None, None]:
    """Reset all module-level global singletons before and after each test.

    Prevents state leakage between test files caused by:
    - store.py:  _store, _questionnaire_store, _response_store singletons
    - dependencies.py: _llm_client, _cost_fuse, _profile_generator, etc.
    - tracker.py: _cost_tracker singleton + persisted state file
    - main.py: FastAPI app.dependency_overrides shared across test files

    Heavy imports (aicbc.main, aicbc.analysis.store, etc.) are resolved lazily
    once and cached so the fixture body is cheap on subsequent calls.
    """
    await _reset_all()
    yield
    await _reset_all()


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


def _mock_llm_response(
    content: dict[str, Any] | str, model: str = "claude-sonnet-4-6"
) -> LLMResponse:
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

    cities = ["一线城市", "新一线城市", "二线城市", "三线城市", "四线城市"]
    incomes = ["15-30万元", "8-15万元", "30-50万元", "15-30万元", "8-15万元"]

    def _default_layer1(idx: int = 0) -> dict[str, Any]:
        return {
            "age": f"{28 + idx}岁",
            "gender": "女",
            "city": cities[idx % len(cities)],
            "income": incomes[idx % len(incomes)],
            "occupation": "互联网产品经理",
            "education": "本科",
            "marital_status": "已婚无孩",
            "living_type": "自有住房（89㎡三居室）",
        }

    def _default_layer2(idx: int = 0) -> dict[str, Any]:
        return {
            "price_sensitivity": "对高频消费品价格敏感，对耐用品愿意为品质溢价",
            "purchase_channels": ["京东自营", "天猫旗舰店", "山姆会员店"],
            "decision_style": "参数党+口碑党混合，购买前必看测评",
            "brand_loyalty": "对信任品牌复购率高，愿意尝试新锐品牌",
            "information_source": ["小红书", "什么值得买", "知乎", "同事推荐"],
        }

    def _default_layer3(idx: int = 0) -> dict[str, Any]:
        return {
            "core_values": ["效率", "品质生活", "家庭至上"],
            "core_anxieties": ["时间不够用", "家务分工矛盾"],
            "tension_combination": {
                "labels": ["精致品质", "凑单退单高手"],
                "narrative_explanation": (
                    f"她追求精致生活却总在凑单后退掉不需要的商品，这种矛盾源于她既想享受品质又害怕浪费金钱的深层焦虑。"
                    f"小时候家境普通让她对浪费极度敏感，成年后收入提升让她有能力追求品质（样本{idx + 1}）。"
                ),
            },
            "secret_motivation": f"用科技产品证明自己的生活品味，缓解同辈压力（样本{idx + 1}）",
            "defense_mechanism": "合理化——把临时消费欲望解释为投资生活品质",
        }

    def _default_layer4(idx: int = 0) -> dict[str, Any]:
        return {
            "daily_routine": f"早7点起床，地铁通勤{40 + idx}分钟，晚7点到家，周末打扫或带孩子上兴趣班",
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
        idx = (_side_effect.call_count - 1) // 5
        layer_idx = (_side_effect.call_count - 1) % 5
        layers = [
            _default_layer1(idx),
            _default_layer2(idx),
            _default_layer3(idx),
            _default_layer4(idx),
            _default_aux(),
        ]
        return _mock_llm_response(layers[layer_idx])

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
# Persona factory
# ---------------------------------------------------------------------------


def persona_factory(
    persona_id: str = "persona-test-001",
    segment: str = "测试群体",
    age: str = "28岁",
    gender: str = "女",
    city: str = "新一线城市",
    income: str = "15-30万元",
    occupation: str = "互联网产品经理",
    education: str = "本科",
    marital_status: str = "已婚无孩",
    living_type: str = "自有住房",
    price_sensitivity: str = "中等敏感",
    purchase_channels: list[str] | None = None,
    decision_style: str = "理性比较型",
    brand_loyalty: str = "中等",
    information_source: list[str] | None = None,
    core_values: list[str] | None = None,
    core_anxieties: list[str] | None = None,
    tension_labels: list[str] | None = None,
    tension_narrative: str | None = None,
    secret_motivation: str = "用科技产品证明品味",
    defense_mechanism: str = "合理化",
    daily_routine: str = "早7点起床，通勤40分钟",
    purchase_trigger: str = "被小红书种草",
    stress_response: str = "焦虑时刷购物APP",
    social_behavior: str = "朋友圈少发",
    samples: list[str] | None = None,
    purchase_constraints: list[str] | None = None,
    decision_factors: list[str] | None = None,
    ignored_factors: list[str] | None = None,
) -> PersonaProfile:
    """Build a PersonaProfile with configurable bias-relevant fields.

    Defaults mirror the original ``_make_persona`` helper so that existing
    unit tests can call ``persona_factory()`` without arguments.  Red-team
    tests override the handful of fields where ``_build_safe_persona`` used
    different defaults.
    """
    return PersonaProfile(
        persona_id=persona_id,
        segment=segment,
        layer1_demographics=Layer1Demographics(
            age=age,
            gender=gender,
            city=city,
            income=income,
            occupation=occupation,
            education=education,
            marital_status=marital_status,
            living_type=living_type,
        ),
        layer2_behavior=Layer2Behavior(
            price_sensitivity=price_sensitivity,
            purchase_channels=purchase_channels or ["京东", "天猫"],
            decision_style=decision_style,
            brand_loyalty=brand_loyalty,
            information_source=information_source or ["小红书", "知乎"],
        ),
        layer3_psychology=Layer3Psychology(
            core_values=core_values or ["效率", "品质"],
            core_anxieties=core_anxieties or ["时间不够"],
            tension_combination=TensionCombination(
                labels=tension_labels or ["A", "B"],
                narrative_explanation=tension_narrative
                or "她追求精致生活却总在凑单后退掉不需要的商品，这种矛盾源于她既想享受品质又害怕浪费金钱的深层焦虑，这是她内心最真实的状态。",
            ),
            secret_motivation=secret_motivation,
            defense_mechanism=defense_mechanism,
        ),
        layer4_scenarios=Layer4Scenarios(
            daily_routine=daily_routine,
            purchase_trigger=purchase_trigger,
            stress_response=stress_response,
            social_behavior=social_behavior,
        ),
        language_samples=samples
        or [
            "洗碗机用起来真的很方便，洗完的碗都亮晶晶的。",
            "对比了好几个品牌，最后还是选了这个性价比高的。",
            "安装师傅非常专业，只用了半小时就全部搞定了。",
        ],
        dishwasher_context=DishwasherContext(
            purchase_constraints=purchase_constraints or ["厨房小"],
            decision_factors=decision_factors or ["价格"],
            ignored_factors=ignored_factors or ["外观"],
        ),
        generation_metadata=GenerationMetadata(),
    )


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
            city="新一线城市",
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
            defense_mechanism="合理化——把临时消费欲望解释为投资生活品质",
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
