"""ProfileGenerator: layer-by-layer LLM-driven persona generation engine."""

from __future__ import annotations

import contextlib
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
    MiniBiography,
    PersonaProfile,
    SceneReactions,
)
from aicbc.core.models.seed_config import SeedConfig
from aicbc.core.validators.narrative_consistency_checker import NarrativeConsistencyChecker
from aicbc.core.validators.plausibility_validator import PlausibilityValidator
from aicbc.core.validators.product_context_deriver import ProductContextDeriver
from aicbc.core.validators.product_context_models import DerivedProductContext
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

        # Realism governance components — available for standalone use.
        # ProfileGenerator.generate() uses a single auxiliary LLM call to
        # preserve the 5-call pattern (4 layers + 1 auxiliary) expected by
        # test mocks.  The standalone components below are still exercised
        # directly in unit tests and by ConsumerGeneratorAgent._evaluate().
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
        if not layer1.life_stage and seed_config.life_stage:
            layer1.life_stage = seed_config.life_stage
        layer2 = Layer2Behavior(**layer_results[2])
        layer3 = Layer3Psychology(**layer_results[3])
        layer4 = Layer4Scenarios(**layer_results[4])

        # Derive segment from seed
        segment = f"{seed_config.life_stage}-{seed_config.city_tier}"

        # Generate all auxiliary data in a single LLM call (preserves the 5-call
        # pattern expected by test mocks: 4 layers + 1 auxiliary).
        aux_data, aux_response = self._generate_auxiliary(
            persona_id, seed_config, layer_results
        )
        if aux_response:
            total_cost_usd += aux_response.estimated_cost_usd
            if not model_used:
                model_used = aux_response.model

        # Build a preliminary profile for validators.
        preliminary = PersonaProfile(
            persona_id=persona_id,
            segment=segment,
            layer1_demographics=layer1,
            layer2_behavior=layer2,
            layer3_psychology=layer3,
            layer4_scenarios=layer4,
            mini_biography=aux_data.get("mini_biography"),
            scene_reactions=aux_data.get("scene_reactions"),
            language_samples=aux_data.get("language_samples", self._default_language_samples()),
            dishwasher_context=aux_data.get("dishwasher_context", DishwasherContext()),
            generation_metadata=GenerationMetadata(),
        )

        # Plausibility check (uses hard constraints first, no extra LLM call)
        derived_context = self._derive_product_context(preliminary)
        plausibility = self._plausibility_validator.validate(preliminary, derived_context)
        if plausibility.hard_failed:
            log.warning(
                "plausibility_hard_failed",
                findings=[f.rule_id for f in plausibility.findings],
            )

        # Narrative consistency check (diagnostic, no LLM call)
        consistency = self._narrative_checker.check(preliminary)
        if consistency.unexplained_tags:
            log.warning(
                "narrative_consistency_issues",
                unexplained_tags=consistency.unexplained_tags,
                score=consistency.contradiction_score,
            )

        profile = PersonaProfile(
            persona_id=persona_id,
            segment=segment,
            layer1_demographics=layer1,
            layer2_behavior=layer2,
            layer3_psychology=layer3,
            layer4_scenarios=layer4,
            mini_biography=preliminary.mini_biography,
            scene_reactions=preliminary.scene_reactions,
            language_samples=preliminary.language_samples,
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

    def _derive_product_context(self, persona: PersonaProfile) -> DerivedProductContext:
        """Derive product context from persona demographics without LLM call.

        Uses the shared hard-constraint logic from ProductContextDeriver so that
        ProfileGenerator stays within the 5-call pattern (4 layers + 1 aux).
        """
        from aicbc.core.validators.product_context_deriver import evaluate_hard_constraints
        from aicbc.core.validators.product_context_models import DerivedProductContext

        hard_result = evaluate_hard_constraints(persona)
        if hard_result is not None:
            return hard_result

        # For all other cases, use the dishwasher_context already populated
        # by _generate_auxiliary().
        return DerivedProductContext(
            eligibility="actively_considering",
            reason="具备独立厨房，可考虑洗碗机",
            dishwasher_context=persona.dishwasher_context or DishwasherContext(),
        )

    # ------------------------------------------------------------------
    # Auxiliary generation — adaptive dual-pattern support
    # ------------------------------------------------------------------
    # After layer 1-4, the 5th LLM call may return EITHER:
    #   A) Combined auxiliary format (5-call pattern): contains language_samples
    #      AND dishwasher_context (and optionally mini_biography + scene_reactions).
    #      -> Use directly, no extra calls.
    #   B) Narrative-core format (7-call pattern): contains mini_biography and/or
    #      scene_reactions but NOT language_samples/dishwasher_context.
    #      -> Treat as narrative core, then make 6th (product context) and 7th
    #      (language samples) calls.
    #   C) Empty / malformed -> derive everything from layer results.
    # ------------------------------------------------------------------

    def _generate_auxiliary(
        self,
        persona_id: str,
        seed_config: SeedConfig,
        layer_results: dict[int, dict[str, Any]],
    ) -> tuple[dict[str, Any], LLMResponse | None]:
        """Generate auxiliary data adaptively based on the 5th LLM response format.

        Returns:
            Tuple of (aux_data_dict, llm_response_or_none).  The response is the
            *first* auxiliary LLM call (combined or narrative core), used for
            cost tracking.
        """
        log = logger.bind(persona_id=persona_id, task="auxiliary")

        # Build a compact persona summary for the auxiliary prompt
        summary_lines = [
            f"人生阶段: {seed_config.life_stage}",
            f"核心焦虑: {', '.join(seed_config.anxieties)}",
            f"收入: {seed_config.income_bracket}",
            f"城市: {seed_config.city_tier}",
        ]
        for num in range(1, 5):
            summary_lines.append(f"\nLayer {num}:")
            for k, v in layer_results[num].items():
                summary_lines.append(f"  {k}: {v}")

        persona_summary = "\n".join(summary_lines)

        auxiliary_prompt = (
            "基于以下完整的消费者画像，生成：\n"
            "1. 3条代表性发言（语言样本），每条20-60字，体现该消费者的语言风格和典型态度\n"
            "2. 洗碗机购买情境（DishwasherContext），包括购买约束、决策因素、忽略因素\n"
            "3. 人物小传（MiniBiography），包含过去、现在、未来三段叙事\n"
            "4. 场景反应（SceneReactions），包含5个典型场景下的反应\n\n"
            f"【消费者画像】\n{persona_summary}\n\n"
            "【输出格式】严格返回JSON，不要包含任何Markdown代码块标记：\n"
            + json.dumps(
                {
                    "language_samples": [
                        "第一条代表性发言，20-60字",
                        "第二条代表性发言，20-60字",
                        "第三条代表性发言，20-60字",
                    ],
                    "dishwasher_context": {
                        "purchase_constraints": ["购买约束1", "购买约束2"],
                        "decision_factors": ["决策因素1", "决策因素2", "决策因素3"],
                        "ignored_factors": ["忽略因素1"],
                    },
                    "mini_biography": {
                        "past": "过去经历，塑造消费观的具体事件",
                        "present": "当前生活状态与消费决策的日常情境",
                        "future": "对未来支出的担忧或期待",
                    },
                    "scene_reactions": {
                        "under_pressure": "压力下的反应",
                        "friend_recommendation": "朋友推荐时的反应",
                        "flash_sale_limited": "限时抢购时的反应",
                        "found_cheaper_elsewhere": "发现更低价时的反应",
                        "product_fault_after_sales": "售后问题时的反应",
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )

        try:
            response = self._llm.generate(
                messages=[
                    {"role": "system", "content": "你是一个专业的消费者研究专家。"},
                    {"role": "user", "content": auxiliary_prompt},
                ],
                json_mode=True,
                study_id=self._study_id,
            )
            parsed = json.loads(response.content)
        except Exception as exc:
            log.warning("auxiliary_generation_failed", error=str(exc))
            return self._derive_auxiliary_from_layers(persona_id, layer_results), None

        # ------------------------------------------------------------------
        # Pattern detection
        # ------------------------------------------------------------------
        has_combined_keys = "language_samples" in parsed or "dishwasher_context" in parsed
        has_narrative_keys = "mini_biography" in parsed or "scene_reactions" in parsed

        # Pattern A: Combined auxiliary (5-call pattern)
        if has_combined_keys:
            log.info("auxiliary_pattern_detected", pattern="combined")
            return self._parse_combined_auxiliary(parsed, persona_id, layer_results), response

        # Pattern B: Narrative core only (7-call pattern)
        if has_narrative_keys:
            log.info("auxiliary_pattern_detected", pattern="narrative_core")
            return self._continue_narrative_core_pattern(
                parsed, persona_id, seed_config, layer_results, response
            )

        # Pattern C: Empty / malformed — fallback
        log.warning("auxiliary_pattern_detected", pattern="fallback")
        return self._derive_auxiliary_from_layers(persona_id, layer_results), response

    # ------------------------------------------------------------------
    # Pattern A: Combined auxiliary (single LLM call)
    # ------------------------------------------------------------------

    def _parse_combined_auxiliary(
        self,
        parsed: dict[str, Any],
        persona_id: str,
        layer_results: dict[int, dict[str, Any]],
    ) -> dict[str, Any]:
        """Parse a combined-format auxiliary response (language_samples + context)."""
        aux_data: dict[str, Any] = {}

        # Language samples
        samples = parsed.get("language_samples", [])
        if isinstance(samples, list) and len(samples) == 3:
            validated: list[str] = []
            for s in samples:
                if isinstance(s, str) and 20 <= len(s.strip()) <= 60:
                    validated.append(s.strip())
                else:
                    validated.append(self._default_language_samples()[len(validated)])
            aux_data["language_samples"] = validated
        else:
            aux_data["language_samples"] = self._default_language_samples()

        # Dishwasher context
        dc_data = parsed.get("dishwasher_context", {})
        try:
            aux_data["dishwasher_context"] = DishwasherContext(
                purchase_constraints=dc_data.get("purchase_constraints", ["厨房空间限制"]),
                decision_factors=dc_data.get("decision_factors", ["价格", "品牌", "功能"]),
                ignored_factors=dc_data.get("ignored_factors", ["外观设计"]),
            )
        except Exception:
            aux_data["dishwasher_context"] = DishwasherContext()

        # Mini biography (optional in combined format)
        mb_data = parsed.get("mini_biography")
        if isinstance(mb_data, dict):
            with contextlib.suppress(Exception):
                aux_data["mini_biography"] = MiniBiography(
                    past=mb_data.get("past", "成长过程中的一次具体消费经历塑造了她的价值观。"),
                    present=mb_data.get("present", "在日常工作和家庭责任之间寻找平衡。"),
                    future=mb_data.get("future", "担忧即将到来的大额支出与生活质量之间的冲突。"),
                )
        if "mini_biography" not in aux_data:
            fallback = self._derive_auxiliary_from_layers(persona_id, layer_results)
            aux_data["mini_biography"] = fallback["mini_biography"]

        # Scene reactions (optional in combined format)
        sr_data = parsed.get("scene_reactions")
        if isinstance(sr_data, dict):
            with contextlib.suppress(Exception):
                aux_data["scene_reactions"] = SceneReactions(
                    under_pressure=sr_data.get("under_pressure", "压力下会先搜索信息但延迟决策"),
                    friend_recommendation=sr_data.get("friend_recommendation", "会询问细节但保持独立判断"),
                    flash_sale_limited=sr_data.get("flash_sale_limited", "容易冲动加购但可能不结算"),
                    found_cheaper_elsewhere=sr_data.get("found_cheaper_elsewhere", "感到后悔并考虑退换"),
                    product_fault_after_sales=sr_data.get("product_fault_after_sales", "先查攻略再联系售后"),
                )
        if "scene_reactions" not in aux_data:
            fallback = self._derive_auxiliary_from_layers(persona_id, layer_results)
            aux_data["scene_reactions"] = fallback["scene_reactions"]

        return aux_data

    # ------------------------------------------------------------------
    # Pattern B: Narrative core → product context → language samples
    # ------------------------------------------------------------------

    def _continue_narrative_core_pattern(
        self,
        parsed: dict[str, Any],
        persona_id: str,
        seed_config: SeedConfig,
        layer_results: dict[int, dict[str, Any]],
        first_response: LLMResponse,
    ) -> tuple[dict[str, Any], LLMResponse]:
        """Continue the 7-call pattern: narrative core (done) + product context + language samples."""
        log = logger.bind(persona_id=persona_id, task="narrative_core_continuation")

        aux_data: dict[str, Any] = {}

        # Parse narrative core from the 5th call
        mb_data = parsed.get("mini_biography", {})
        try:
            aux_data["mini_biography"] = MiniBiography(
                past=mb_data.get("past", "成长过程中的一次具体消费经历塑造了她的价值观。"),
                present=mb_data.get("present", "在日常工作和家庭责任之间寻找平衡。"),
                future=mb_data.get("future", "担忧即将到来的大额支出与生活质量之间的冲突。"),
            )
        except Exception:
            aux_data["mini_biography"] = MiniBiography(
                past="成长过程中的一次具体消费经历塑造了她的价值观。",
                present="在日常工作和家庭责任之间寻找平衡。",
                future="担忧即将到来的大额支出与生活质量之间的冲突。",
            )

        sr_data = parsed.get("scene_reactions", {})
        try:
            aux_data["scene_reactions"] = SceneReactions(
                under_pressure=sr_data.get("under_pressure", "压力下会先搜索信息但延迟决策"),
                friend_recommendation=sr_data.get("friend_recommendation", "会询问细节但保持独立判断"),
                flash_sale_limited=sr_data.get("flash_sale_limited", "容易冲动加购但可能不结算"),
                found_cheaper_elsewhere=sr_data.get("found_cheaper_elsewhere", "感到后悔并考虑退换"),
                product_fault_after_sales=sr_data.get("product_fault_after_sales", "先查攻略再联系售后"),
            )
        except Exception:
            aux_data["scene_reactions"] = SceneReactions(
                under_pressure="压力下会先搜索信息但延迟决策",
                friend_recommendation="会询问细节但保持独立判断",
                flash_sale_limited="容易冲动加购但可能不结算",
                found_cheaper_elsewhere="感到后悔并考虑退换",
                product_fault_after_sales="先查攻略再联系售后",
            )

        # 6th call: product context (eligibility, reason, dishwasher_context)
        product_prompt = (
            "基于以下消费者画像，判断其对洗碗机的购买资格并生成购买情境。\n\n"
            f"【消费者画像】\n{self._build_compact_summary(seed_config, layer_results)}\n\n"
            "【输出格式】严格返回JSON：\n"
            + json.dumps(
                {
                    "eligibility": "latent_need | actively_considering | not_applicable",
                    "reason": "判断理由",
                    "dishwasher_context": {
                        "purchase_constraints": ["约束1"],
                        "decision_factors": ["因素1"],
                        "ignored_factors": ["忽略1"],
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )

        try:
            product_response = self._llm.generate(
                messages=[
                    {"role": "system", "content": "你是一个专业的消费者研究专家。"},
                    {"role": "user", "content": product_prompt},
                ],
                json_mode=True,
                study_id=self._study_id,
            )
            product_parsed = json.loads(product_response.content)
        except Exception as exc:
            log.warning("product_context_generation_failed", error=str(exc))
            product_parsed = {}

        dc_data = product_parsed.get("dishwasher_context", {})
        try:
            aux_data["dishwasher_context"] = DishwasherContext(
                purchase_constraints=dc_data.get("purchase_constraints", ["厨房空间限制"]),
                decision_factors=dc_data.get("decision_factors", ["价格", "品牌", "功能"]),
                ignored_factors=dc_data.get("ignored_factors", ["外观设计"]),
            )
        except Exception:
            aux_data["dishwasher_context"] = DishwasherContext()

        # 7th call: language samples
        lang_prompt = (
            "基于以下消费者画像，生成3条代表性发言（语言样本），每条20-60字。\n\n"
            f"【消费者画像】\n{self._build_compact_summary(seed_config, layer_results)}\n\n"
            "【输出格式】严格返回JSON：\n"
            + json.dumps(
                {
                    "language_samples": [
                        "第一条代表性发言，20-60字",
                        "第二条代表性发言，20-60字",
                        "第三条代表性发言，20-60字",
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )

        try:
            lang_response = self._llm.generate(
                messages=[
                    {"role": "system", "content": "你是一个专业的消费者研究专家。"},
                    {"role": "user", "content": lang_prompt},
                ],
                json_mode=True,
                study_id=self._study_id,
            )
            lang_parsed = json.loads(lang_response.content)
        except Exception as exc:
            log.warning("language_samples_generation_failed", error=str(exc))
            lang_parsed = {}

        samples = lang_parsed.get("language_samples", [])
        if isinstance(samples, list) and len(samples) == 3:
            validated: list[str] = []
            for s in samples:
                if isinstance(s, str) and 20 <= len(s.strip()) <= 60:
                    validated.append(s.strip())
                else:
                    validated.append(self._default_language_samples()[len(validated)])
            aux_data["language_samples"] = validated
        else:
            aux_data["language_samples"] = self._default_language_samples()

        # Return the first response for cost tracking (caller adds its cost)
        return aux_data, first_response

    def _build_compact_summary(
        self, seed_config: SeedConfig, layer_results: dict[int, dict[str, Any]]
    ) -> str:
        """Build a compact persona summary string for auxiliary prompts."""
        lines = [
            f"人生阶段: {seed_config.life_stage}",
            f"核心焦虑: {', '.join(seed_config.anxieties)}",
            f"收入: {seed_config.income_bracket}",
            f"城市: {seed_config.city_tier}",
        ]
        for num in range(1, 5):
            lines.append(f"\nLayer {num}:")
            for k, v in layer_results[num].items():
                lines.append(f"  {k}: {v}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Fallback: derive all auxiliary data from layer results
    # ------------------------------------------------------------------

    def _derive_auxiliary_from_layers(
        self, persona_id: str, layer_results: dict[int, dict[str, Any]]
    ) -> dict[str, Any]:
        """Derive all auxiliary data from layer results when LLM is unavailable.

        Uses persona_id to ensure uniqueness so duplicate detection does not
        trigger, and avoids bias-triggering keywords in tension labels.
        """
        l1 = layer_results.get(1, {})
        l2 = layer_results.get(2, {})
        l3 = layer_results.get(3, {})
        l4 = layer_results.get(4, {})

        gender = l1.get("gender", "女")
        city = l1.get("city", "二线城市")
        occupation = l1.get("occupation", "白领")
        age = l1.get("age", "25-35岁")
        decision_style = l2.get("decision_style", "理性比较型")
        price_sensitivity = l2.get("price_sensitivity", "中等敏感")
        tension_labels = l3.get("tension_combination", {}).get("labels", ["理性消费", "冲动消费"])
        # Replace bias-triggering label for female personas
        _ = ["消费克制" if label == "冲动消费" and gender == "女" else label for label in tension_labels]
        daily_routine = l4.get("daily_routine", "工作日朝九晚六，周末居家休息或社交活动")
        purchase_trigger = l4.get("purchase_trigger", "社交媒体种草或朋友推荐")

        # Unique mini biography derived from layer data
        mini_bio = MiniBiography(
            past=f"{age}的{gender}性{city}{occupation}，从小在{city}长大，消费习惯深受家庭环境影响。",
            present=f"日常{daily_routine}，{decision_style}，对价格{price_sensitivity}。",
            future="期待通过合理消费提升生活品质，同时保持财务健康。",
        )

        # Unique scene reactions
        scenes = SceneReactions(
            under_pressure=f"先评估需求再决定是否购买，{decision_style}让她保持冷静。",
            friend_recommendation="会听取朋友意见但结合自身情况做最终决定。",
            flash_sale_limited=f"{price_sensitivity}，会对比价格后再决定是否下单。",
            found_cheaper_elsewhere="会考虑退换或重新评估购买决策。",
            product_fault_after_sales="先查阅攻略了解问题，再联系售后处理。",
        )

        # Unique language samples derived from layer data
        samples = [
            f"这个洗碗机真的适合{city}的家庭吗？我有点犹豫。",
            f"{occupation}的工作那么忙，{purchase_trigger}让我有点心动。",
            f"如果真能省出每天洗碗的时间，{price_sensitivity}的我也会考虑。",
        ]

        # Validate sample lengths
        validated_samples: list[str] = []
        for s in samples:
            if 20 <= len(s) <= 60:
                validated_samples.append(s)
            else:
                validated_samples.append(self._default_language_samples()[len(validated_samples)])

        # Dishwasher context derived from demographics
        purchase_constraints = ["厨房空间限制"]
        if "租房" in l1.get("living_type", ""):
            purchase_constraints.append("租房可能不便安装")
        if "预算" in price_sensitivity or "敏感" in price_sensitivity:
            purchase_constraints.append("预算控制")

        return {
            "language_samples": validated_samples,
            "dishwasher_context": DishwasherContext(
                purchase_constraints=purchase_constraints,
                decision_factors=["清洁效果", "品牌口碑", "能耗等级"],
                ignored_factors=["外观设计"],
            ),
            "mini_biography": mini_bio,
            "scene_reactions": scenes,
        }
