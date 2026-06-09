"""Development server with mocked LLM for endpoint verification."""

import json
from typing import Any
from unittest.mock import MagicMock

from aicbc.api.dependencies import (
    get_llm_client,
    get_logic_validator,
    get_profile_generator,
    get_schema_validator,
    get_seed_generator,
)
from aicbc.core.store import get_store
from aicbc.core.validators import LogicValidator, SchemaValidator
from aicbc.generators.profile_generator import ProfileGenerator
from aicbc.generators.seed_generator import SeedGenerator
from aicbc.llm.client import LLMResponse, Provider
from aicbc.main import app


def _mock_resp(content: dict[str, Any] | str, model: str = "claude-sonnet-4-6") -> LLMResponse:
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


def _l1() -> dict[str, Any]:
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


def _l2() -> dict[str, Any]:
    return {
        "price_sensitivity": "对高频消费品价格敏感，对耐用品愿意为品质溢价",
        "purchase_channels": ["京东自营", "天猫旗舰店", "山姆会员店"],
        "decision_style": "参数党+口碑党混合，购买前必看测评",
        "brand_loyalty": "对信任品牌复购率高，愿意尝试新锐品牌",
        "information_source": ["小红书", "什么值得买", "知乎", "同事推荐"],
    }


def _l3() -> dict[str, Any]:
    return {
        "core_values": ["效率", "品质生活", "家庭至上"],
        "core_anxieties": ["时间不够用", "家务分工矛盾"],
        "tension_combination": {
            "labels": ["精致品质", "凑单退单高手"],
            "narrative_explanation": (
                "她追求精致生活却总在凑单后退掉不需要的商品，这种矛盾源于她既想享受品质又害怕浪费金钱的深层焦虑。"
                "小时候家境普通让她对浪费极度敏感，成年后收入提升让她有能力追求品质，但童年的匮乏感仍在潜意识中支配着她的消费决策。"
            ),
        },
        "secret_motivation": "用科技产品证明自己的生活品味，缓解同辈压力",
        "defense_mechanism": "合理化——把冲动消费解释为投资生活品质",
    }


def _l4() -> dict[str, Any]:
    return {
        "daily_routine": "早7点起床，地铁通勤40分钟，晚7点到家，周末打扫或带孩子上兴趣班",
        "purchase_trigger": "被小红书提升幸福感的小家电种草，叠加同事推荐",
        "stress_response": "焦虑时刷购物APP加购，冷静后删除，形成加购-删除循环",
        "social_behavior": "朋友圈极少发消费内容，但在私域社群活跃分享购物攻略",
    }


def _aux() -> dict[str, Any]:
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


# Build mock client
client = MagicMock()


def _side_effect(*args: Any, **kwargs: Any) -> LLMResponse:
    if not hasattr(_side_effect, "call_count"):
        _side_effect.call_count = 0
    _side_effect.call_count += 1
    idx = (_side_effect.call_count - 1) % 5
    layers = [_l1(), _l2(), _l3(), _l4(), _aux()]
    return _mock_resp(layers[idx])


client.generate.side_effect = _side_effect

# Override dependencies
app.dependency_overrides[get_llm_client] = lambda: client
app.dependency_overrides[get_seed_generator] = lambda: SeedGenerator(seed=42)
app.dependency_overrides[get_profile_generator] = lambda: ProfileGenerator(llm_client=client)
app.dependency_overrides[get_schema_validator] = SchemaValidator
app.dependency_overrides[get_logic_validator] = LogicValidator
app.dependency_overrides[get_store] = get_store

if __name__ == "__main__":
    import uvicorn

    print("Starting AI_CBC dev server with mocked LLM on http://127.0.0.1:8000")
    print("Endpoints:")
    print("  POST /api/v1/personas/generate")
    print("  GET  /api/v1/personas")
    print("  GET  /api/v1/personas/{id}")
    print("  POST /api/v1/personas/{id}/validate")
    print("  GET  /api/v1/personas/{id}/layers/{n}")
    print("  DELETE /api/v1/personas/{id}")
    print()
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
