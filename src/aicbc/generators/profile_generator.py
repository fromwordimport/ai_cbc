"""ProfileGenerator: layer-by-layer LLM-driven persona generation engine."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import structlog

from aicbc.core.models.persona import (
    DishwasherContext,
    GenerationMetadata,
    Layer1Demographics,
    Layer2Behavior,
    Layer3Psychology,
    Layer4Scenarios,
    PersonaProfile,
)
from aicbc.core.models.seed_config import SeedConfig
from aicbc.core.validators.narrative_consistency_checker import NarrativeConsistencyChecker
from aicbc.core.validators.plausibility_validator import PlausibilityValidator
from aicbc.core.validators.product_context_deriver import ProductContextDeriver
from aicbc.generators.language_sample_generator import LanguageSampleGenerator
from aicbc.generators.narrative_core_generator import NarrativeCoreGenerator
from aicbc.llm.client import LLMClient, LLMResponse

logger = structlog.get_logger("aicbc.generators")

# Default prompt template path
DEFAULT_PROMPT_PATH = Path(__file__).parents[3] / "configs" / "prompts" / "persona_generation.txt"

# Layer metadata for prompt construction
_LAYER_META: dict[int, dict[str, Any]] = {
    1: {
        "name": "Layer 1: 人口统计层 (Demographics)",
        "description": "生成消费者的基础人口统计信息",
        "fields": [
            "age",
            "gender",
            "city",
            "income",
            "occupation",
            "education",
            "marital_status",
            "living_type",
        ],
    },
    2: {
        "name": "Layer 2: 消费行为层 (Behavior)",
        "description": "基于Layer 1的人口统计信息，生成消费行为特征",
        "fields": [
            "price_sensitivity",
            "purchase_channels",
            "decision_style",
            "brand_loyalty",
            "information_source",
        ],
    },
    3: {
        "name": "Layer 3: 心理动机层 (Psychology)",
        "description": "基于Layer 1-2的信息，生成深层心理动机和张力组合",
        "fields": [
            "core_values",
            "core_anxieties",
            "tension_combination",
            "secret_motivation",
            "defense_mechanism",
        ],
    },
    4: {
        "name": "Layer 4: 情境叙事层 (Scenarios)",
        "description": "基于Layer 1-3的信息，生成日常生活情境和叙事",
        "fields": ["daily_routine", "purchase_trigger", "stress_response", "social_behavior"],
    },
}

# JSON schema snippets injected per layer
_LAYER_JSON_SCHEMA: dict[int, str] = {
    1: json.dumps(
        {
            "age": "年龄段，如'28-32岁'",
            "gender": "性别，如'男'或'女'",
            "city": "现居城市/区域，如'杭州（新一线城市）'",
            "income": "个人年收入档位，如'15-30万元'",
            "occupation": "职业，如'互联网产品经理'",
            "education": "教育程度，如'本科'",
            "marital_status": "婚姻状况，如'已婚，育有一子（3岁）'",
            "living_type": "居住形态，如'自有住房（90㎡两居室）'",
        },
        ensure_ascii=False,
        indent=2,
    ),
    2: json.dumps(
        {
            "price_sensitivity": "价格敏感度描述，如'对高频消费品价格敏感，对耐用品愿意为品质溢价'",
            "purchase_channels": ["常用购买渠道列表，如'京东自营', '山姆会员店', '品牌官方小程序'"],
            "decision_style": "决策风格，如'参数党+口碑党混合，购买前必看测评'",
            "brand_loyalty": "品牌忠诚度，如'对信任品牌有较高忠诚度，但愿意尝试新品牌'",
            "information_source": ["信息来源列表，如'小红书', '什么值得买', '同事推荐'"],
        },
        ensure_ascii=False,
        indent=2,
    ),
    3: json.dumps(
        {
            "core_values": ["核心价值观列表，如'家庭至上', '效率优先', '性价比为王'"],
            "core_anxieties": ["核心焦虑列表，如'育儿焦虑', '同辈压力', '健康焦虑'"],
            "tension_combination": {
                "labels": ["矛盾标签组合，如'高收入', '极简主义'"],
                "narrative_explanation": "对张力组合的心理叙事解释，至少50字。如：'她年收入40万却坚持极简生活，源于童年物质匮乏的记忆。她通过控制消费来获得安全感，但内心深处渴望通过消费证明自我价值。这种矛盾让她在大促时疯狂囤货后又大量退货。'",
            },
            "secret_motivation": "隐藏动机，如'表面上说买洗碗机是为了节省时间，真实动机是想减少与婆婆因家务产生的摩擦'",
            "defense_mechanism": "心理防御机制，如'合理化——把冲动消费解释为'投资生活品质''",
        },
        ensure_ascii=False,
        indent=2,
    ),
    4: json.dumps(
        {
            "daily_routine": "日常生活轨迹，如'早7点起床，通勤1小时，晚8点到家，周末带孩子上兴趣班'",
            "purchase_trigger": "购买触发事件，如'看到同事家洗碗机后产生兴趣，被小红书种草文强化'",
            "stress_response": "压力下的反应，如'焦虑时会刷购物APP，但经常加购不结算'",
            "social_behavior": "社交行为特征，如'朋友圈极少发消费相关内容，但在私域社群活跃'",
        },
        ensure_ascii=False,
        indent=2,
    ),
}

# Default fallback values per layer (used when LLM parsing fails)
_LAYER_FALLBACKS: dict[int, dict[str, Any]] = {
    1: {
        "age": "25-35岁",
        "gender": "女",
        "city": "二线城市",
        "income": "8-15万元",
        "occupation": "白领",
        "education": "本科",
        "marital_status": "未婚",
        "living_type": "租房独居",
    },
    2: {
        "price_sensitivity": "中等敏感",
        "purchase_channels": ["电商平台", "线下商超"],
        "decision_style": "理性比较型",
        "brand_loyalty": "中等忠诚度",
        "information_source": ["社交媒体", "朋友推荐"],
    },
    3: {
        "core_values": ["家庭", "健康", "效率"],
        "core_anxieties": ["同辈压力"],
        "tension_combination": {
            "labels": ["理性消费", "冲动消费"],
            "narrative_explanation": "内心渴望理性消费以积累财富，但面对情绪压力时容易冲动购物，事后又陷入自责。这种循环源于对自我控制力的不确定感。",
        },
        "secret_motivation": "希望通过消费获得社会认同和归属感",
        "defense_mechanism": "合理化——将非必要消费解释为对自己的奖励",
    },
    4: {
        "daily_routine": "工作日朝九晚六，周末居家休息或社交活动",
        "purchase_trigger": "社交媒体种草或朋友推荐",
        "stress_response": "倾向于通过购物缓解压力",
        "social_behavior": "线上活跃，线下选择性社交",
    },
}


class ProfileGenerationError(Exception):
    """Raised when profile generation encounters an unrecoverable error."""

    pass


class ProfileGenerator:
    """Generates complete four-layer PersonaProfile using an LLM client.

    The generator follows a sequential layer strategy (Layer1 -> Layer2 ->
    Layer3 -> Layer4).  Each layer receives the context of all previously
    generated layers so that upper layers can explain anomalies in lower
    layers (张力优先 / Tension First).

    Error handling is per-layer: if a single layer fails to parse, a
    statically-defined fallback dict is substituted and generation
    continues so that the overall flow is not interrupted.

    **LLM Response Caching**: The underlying ``LLMClient`` maintains an
    in-memory LRU cache (128 entries, thread-safe).  Because all layer
    prompts are fully deterministic given a ``SeedConfig``, repeating a
    ``generate()`` call with the same seed configuration will hit the cache
    for every layer + auxiliary call, reducing latency to near-zero and
    eliminating duplicate API costs.
    """

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        prompt_template_path: Path | str | None = None,
        study_id: str | None = None,
    ) -> None:
        """Initialize the profile generator.

        Args:
            llm_client: An LLMClient instance. If None, a new one is created.
            prompt_template_path: Path to the Jinja2-style prompt template file.
                Defaults to ``configs/prompts/persona_generation.txt``.
            study_id: Optional study identifier for cost tracking.
        """
        self._llm = llm_client or LLMClient()
        self._prompt_path = (
            Path(prompt_template_path) if prompt_template_path else DEFAULT_PROMPT_PATH
        )
        self._template = self._load_template()
        self._study_id = study_id

        self._narrative_gen = NarrativeCoreGenerator(llm_client=self._llm)
        self._product_deriver = ProductContextDeriver(llm_client=self._llm)
        self._plausibility_validator = PlausibilityValidator()
        self._language_gen = LanguageSampleGenerator(llm_client=self._llm)
        self._narrative_checker = NarrativeConsistencyChecker()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self, persona_id: str, seed_config: SeedConfig, feedback: str | None = None
    ) -> PersonaProfile:
        """Generate a complete four-layer persona profile.

        Args:
            persona_id: Globally unique persona identifier.
            seed_config: Seed configuration produced by SeedGenerator.
            feedback: Optional correction feedback from the evaluation chain.
                When provided, it is injected into the layer-generation prompts
                so the LLM can address specific quality issues (e.g. low
                authenticity scores, contradictory traits).

        Returns:
            A fully populated PersonaProfile.
        """
        log = logger.bind(persona_id=persona_id)
        log.info("profile_generation_start", seed=seed_config.model_dump())

        layer_results: dict[int, dict[str, Any]] = {}
        total_cost_usd = 0.0
        model_used = ""

        for layer_num in range(1, 5):
            # Only layer 1 receives correction feedback; it cascades through
            # previous_layers context to subsequent layers.
            layer_feedback = feedback if layer_num == 1 else None
            layer_data, response = self._generate_layer(
                layer_num, seed_config, layer_results, feedback=layer_feedback
            )
            layer_results[layer_num] = layer_data
            if response:
                total_cost_usd += response.estimated_cost_usd
                if not model_used:
                    model_used = response.model

        # Build layer objects (fallbacks already applied inside _generate_layer)
        layer1 = Layer1Demographics(**layer_results[1])
        layer2 = Layer2Behavior(**layer_results[2])
        layer3 = Layer3Psychology(**layer_results[3])
        layer4 = Layer4Scenarios(**layer_results[4])

        # Derive segment from seed
        segment = f"{seed_config.life_stage}-{seed_config.city_tier}"

        # Build a preliminary profile for narrative/core derivation.
        preliminary = PersonaProfile(
            persona_id=persona_id,
            segment=segment,
            layer1_demographics=layer1,
            layer2_behavior=layer2,
            layer3_psychology=layer3,
            layer4_scenarios=layer4,
            language_samples=self._default_language_samples(),
            dishwasher_context=DishwasherContext(),
            generation_metadata=GenerationMetadata(),
        )

        # Narrative core
        mini_biography, scene_reactions = self._narrative_gen.generate(preliminary)
        preliminary.mini_biography = mini_biography
        preliminary.scene_reactions = scene_reactions

        # Product context derivation
        derived_context = self._product_deriver.derive(preliminary)
        preliminary.dishwasher_context = derived_context.dishwasher_context

        # Plausibility check
        plausibility = self._plausibility_validator.validate(preliminary, derived_context)
        if plausibility.hard_failed:
            log.warning(
                "plausibility_hard_failed",
                findings=[f.rule_id for f in plausibility.findings],
            )
            # We still return the profile; the agent decides whether to regenerate.

        # Narrative consistency check (diagnostic)
        consistency = self._narrative_checker.check(preliminary)
        if consistency.unexplained_tags:
            log.warning(
                "narrative_consistency_issues",
                unexplained_tags=consistency.unexplained_tags,
                score=consistency.contradiction_score,
            )

        # Language samples from narrative core
        language_samples = self._language_gen.generate(preliminary)

        profile = PersonaProfile(
            persona_id=persona_id,
            segment=segment,
            layer1_demographics=layer1,
            layer2_behavior=layer2,
            layer3_psychology=layer3,
            layer4_scenarios=layer4,
            mini_biography=mini_biography,
            scene_reactions=scene_reactions,
            language_samples=language_samples,
            dishwasher_context=derived_context.dishwasher_context,
            generation_metadata=GenerationMetadata(
                model=model_used or "unknown",
                version="1.0",
                seed=None,
                cost_cny=round(total_cost_usd * 7.2, 4),
            ),
        )

        log.info(
            "profile_generation_complete",
            segment=segment,
            cost_cny=profile.generation_metadata.cost_cny,
            plausibility_passed=plausibility.passed,
            narrative_score=consistency.contradiction_score,
            llm_cache_hits=self._llm.cache_hits,
            llm_cache_misses=self._llm.cache_misses,
            llm_cache_size=self._llm.cache_size,
        )
        return profile

    # ------------------------------------------------------------------
    # Prompt builder
    # ------------------------------------------------------------------

    def _load_template(self) -> str:
        """Load the prompt template from disk."""
        if not self._prompt_path.exists():
            raise ProfileGenerationError(f"Prompt template not found: {self._prompt_path}")
        return self._prompt_path.read_text(encoding="utf-8")

    def _build_prompt(
        self,
        layer_num: int,
        seed_config: SeedConfig,
        previous_layers: dict[int, dict[str, Any]],
        feedback: str | None = None,
    ) -> str:
        """Construct the prompt for a specific layer using simple string substitution.

        Args:
            layer_num: The layer to generate (1-4).
            seed_config: The seed configuration.
            previous_layers: Dict of already-generated layer data.
            feedback: Optional correction feedback injected as a prompt block.

        Returns:
            A fully rendered prompt string.
        """
        meta = _LAYER_META[layer_num]
        tension_pairs_str = (
            "\n".join(
                f"  - {p.tag_a} vs {p.tag_b} (张力值: {p.tension_value}): {p.narrative}"
                for p in seed_config.tension_pairs
            )
            or "  无预定义张力组合"
        )

        previous_layers_str = ""
        if previous_layers:
            parts = []
            for num in sorted(previous_layers):
                parts.append(f"  Layer {num} ({_LAYER_META[num]['name']}):")
                for k, v in previous_layers[num].items():
                    parts.append(f"    {k}: {v}")
            previous_layers_str = "\n".join(parts)

        # Build correction feedback block (only for layer 1 — it cascades via previous_layers)
        feedback_block = ""
        if feedback and layer_num == 1:
            feedback_block = (
                "\n【上一轮生成的质量反馈 — 请在本次生成中修正以下问题】\n"
                f"{feedback}\n"
                "请确保本次生成的画像能够解决上述问题，同时保持人格的一致性和真实感。\n"
            )

        # Simple variable substitution (Jinja2-style {{var}})
        prompt = self._template
        replacements = {
            "{{life_stage}}": seed_config.life_stage,
            "{{anxieties}}": ", ".join(seed_config.anxieties),
            "{{income_bracket}}": seed_config.income_bracket,
            "{{city_tier}}": seed_config.city_tier,
            "{{tension_pairs}}": "\n" + tension_pairs_str,
            "{{previous_layers}}": previous_layers_str,
            "{{correction_feedback}}": feedback_block,
            "{{target_layer}}": f"{meta['name']}\n{meta['description']}",
            "{{json_schema}}": _LAYER_JSON_SCHEMA[layer_num],
        }

        for placeholder, value in replacements.items():
            prompt = prompt.replace(placeholder, value)

        # Clean up empty conditional blocks
        prompt = re.sub(r"{%\s*if\s+previous_layers\s*%}\s*{%\s*endif\s*%}", "", prompt)
        prompt = re.sub(r"{%\s*endif\s*%}", "", prompt)

        return prompt

    # ------------------------------------------------------------------
    # Layer generation
    # ------------------------------------------------------------------

    def _generate_layer(
        self,
        layer_num: int,
        seed_config: SeedConfig,
        previous_layers: dict[int, dict[str, Any]],
        feedback: str | None = None,
    ) -> tuple[dict[str, Any], LLMResponse | None]:
        """Generate a single layer via LLM with fallback on failure."""
        log = logger.bind(layer=layer_num)
        prompt = self._build_prompt(layer_num, seed_config, previous_layers, feedback)

        try:
            response = self._llm.generate(
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个专业的消费者研究专家，擅长生成真实、立体的消费者画像。",
                    },
                    {"role": "user", "content": prompt},
                ],
                json_mode=True,
                study_id=self._study_id,
            )
        except Exception as exc:
            log.warning("llm_layer_generation_failed", error=str(exc), layer=layer_num)
            return _LAYER_FALLBACKS[layer_num].copy(), None

        try:
            parsed = json.loads(response.content)
        except json.JSONDecodeError as exc:
            log.warning("layer_json_parse_failed", error=str(exc), content=response.content[:500])
            return _LAYER_FALLBACKS[layer_num].copy(), response

        # Validate that all expected fields are present; fill missing ones from fallback
        fallback = _LAYER_FALLBACKS[layer_num]
        validated = {}
        for key in fallback:
            if key in parsed and parsed[key] is not None:
                validated[key] = parsed[key]
            else:
                log.warning("layer_field_missing", field=key, layer=layer_num)
                validated[key] = fallback[key]

        # Extra fields from LLM are preserved
        for key, value in parsed.items():
            if key not in validated:
                validated[key] = value

        log.info("layer_generation_success", layer=layer_num)
        return validated, response

    @staticmethod
    def _default_language_samples() -> list[str]:
        """Return default language samples for the preliminary profile."""
        return [
            "这个洗碗机真的好用吗？我看网上评价褒贬不一，有点纠结。",
            "价格倒是其次，主要是怕买了之后家里老人不会用，放着积灰。",
            "如果真能省出每天洗碗的时间，我觉得多花点钱也值得考虑。",
        ]
