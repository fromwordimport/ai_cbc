"""SeedGenerator: generates consumer seed configurations with tension-aware sampling."""

from __future__ import annotations

import random
from typing import Any

from aicbc.core.models.seed_config import SeedConfig, TensionPair


# ---------------------------------------------------------------------------
# Static configuration tables derived from the tag system and design docs.
# ---------------------------------------------------------------------------

LIFE_STAGES: list[str] = [
    "学生",
    "初入职场单身",
    "恋爱/新婚无孩",
    "养育幼儿（0-6岁）",
    "养育学龄孩子（7-18岁）",
    "中年空巢（子女独立）",
    "退休生活",
    "独居",
    "合租/群居",
]

# Weights loosely calibrated so that the "most common" life stages in a
# general population sample appear more often.  Higher weight = higher
# probability during weighted sampling.
LIFE_STAGE_WEIGHTS: list[float] = [
    0.10,  # 学生
    0.15,  # 初入职场单身
    0.10,  # 恋爱/新婚无孩
    0.12,  # 养育幼儿（0-6岁）
    0.12,  # 养育学龄孩子（7-18岁）
    0.08,  # 中年空巢（子女独立）
    0.10,  # 退休生活
    0.13,  # 独居
    0.10,  # 合租/群居
]

CITY_TIERS: list[str] = [
    "一线城市",
    "新一线城市",
    "二线城市",
    "三四线城市",
    "县城/乡镇",
]

CITY_TIER_WEIGHTS: list[float] = [
    0.15,  # 一线城市
    0.20,  # 新一线城市
    0.25,  # 二线城市
    0.25,  # 三四线城市
    0.15,  # 县城/乡镇
]

# Mapping from life stage to likely anxiety labels.
LIFE_STAGE_ANXIETY_MAP: dict[str, list[str]] = {
    "学生": ["同辈压力", "身份迷茫/转型期"],
    "初入职场单身": ["同辈压力", "35岁焦虑", "职业倦怠"],
    "恋爱/新婚无孩": ["同辈压力", "中年危机"],
    "养育幼儿（0-6岁）": ["育儿焦虑", "同辈压力", "健康焦虑"],
    "养育学龄孩子（7-18岁）": ["育儿焦虑", "同辈压力", "养老焦虑"],
    "中年空巢（子女独立）": ["中年危机", "养老焦虑", "健康焦虑"],
    "退休生活": ["养老焦虑", "健康焦虑", "身份迷茫/转型期"],
    "独居": ["同辈压力", "身份迷茫/转型期", "健康焦虑"],
    "合租/群居": ["同辈压力", "职业倦怠", "身份迷茫/转型期"],
}

# Income brackets used across the system.
INCOME_BRACKETS: list[str] = [
    "无收入",
    "3万元以下",
    "3-8万元",
    "8-15万元",
    "15-30万元",
    "30-50万元",
    "50-100万元",
    "100万元以上",
]

# Base income distribution (weights per bracket) used as a prior.
# Ordered from low to high.
INCOME_BASE_WEIGHTS: list[float] = [
    0.05,  # 无收入
    0.10,  # 3万元以下
    0.20,  # 3-8万元
    0.25,  # 8-15万元
    0.20,  # 15-30万元
    0.12,  # 30-50万元
    0.06,  # 50-100万元
    0.02,  # 100万元以上
]

# City-tier multipliers shift the income distribution up or down.
# Tier 1 cities bias toward higher incomes; lower tiers bias downward.
CITY_TIER_INCOME_MULTIPLIERS: dict[str, list[float]] = {
    "一线城市":       [0.01, 0.02, 0.05, 0.15, 0.25, 0.28, 0.18, 0.06],
    "新一线城市":     [0.02, 0.04, 0.10, 0.22, 0.25, 0.22, 0.11, 0.04],
    "二线城市":       [0.03, 0.06, 0.15, 0.28, 0.22, 0.15, 0.08, 0.03],
    "三四线城市":     [0.05, 0.12, 0.25, 0.28, 0.18, 0.08, 0.03, 0.01],
    "县城/乡镇":      [0.08, 0.18, 0.30, 0.25, 0.12, 0.05, 0.02, 0.00],
}

# Life-stage income adjustments: some stages have hard constraints or
# strong biases (e.g. students are unlikely to have high incomes).
LIFE_STAGE_INCOME_CONSTRAINTS: dict[str, dict[str, Any]] = {
    "学生": {"max_bracket_index": 3, "bias": "low"},
    "退休生活": {"bias": "low"},
    "初入职场单身": {"bias": "low_mid"},
    "中年空巢（子女独立）": {"bias": "mid_high"},
}

# ---------------------------------------------------------------------------
# Tension definitions
# ---------------------------------------------------------------------------

# Predefined contradictory tag combinations with base tension values.
# Each entry: (tag_a, tag_b, base_tension, narrative_template)
TENSION_DEFINITIONS: list[tuple[str, str, float, str]] = [
    (
        "高收入",
        "极简主义",
        0.75,
        "有钱但怕'被宰'，省钱是游戏而非必需",
    ),
    (
        "高收入",
        "对促销高度敏感",
        0.70,
        "拥有充足购买力，却对每一分优惠斤斤计较",
    ),
    (
        "数码极客",
        "厌恶算法推荐",
        0.80,
        "用技术对抗技术，在研究算法的同时被算法捕获",
    ),
    (
        "精致品质生活",
        "凑单退单高手",
        0.65,
        "在'体面'和'划算'之间走钢丝",
    ),
    (
        "理性比价/精明型",
        "为情绪价值买单",
        0.70,
        "大脑说不要，身体很诚实",
    ),
    (
        "极简社交",
        "私域社群活跃者",
        0.60,
        "只在感到安全的封闭空间里表达",
    ),
    (
        "超前消费/信贷型",
        "极简主义/断舍离",
        0.75,
        "用'买更好的'来合理化'买更多'",
    ),
    (
        "本土主义/国潮信仰",
        "全球化/世界公民",
        0.55,
        "对外展示国潮，对内渴望进口品质",
    ),
    (
        "量入为出/储蓄型",
        "体验消费/享受型",
        0.60,
        "渴望体验却受制于储蓄本能的内心拉锯",
    ),
    (
        "躺平/低欲望",
        "内卷/奋斗",
        0.85,
        "想卷卷不动，想躺躺不平的45度青年",
    ),
]

# Tag synonyms / aliases used for fuzzy matching during tension detection.
TAG_ALIASES: dict[str, list[str]] = {
    "高收入": ["高收入", "50-100万元", "100万元以上", "30-50万元"],
    "极简主义": ["极简主义", "极简主义/断舍离", "断舍离", "简约质朴"],
    "对促销高度敏感": ["对促销高度敏感", "高度敏感（促销驱动决策）", "促销参与深度（大促攻略研究者）"],
    "数码极客": ["数码极客", "科技极客", "IT/互联网/通信"],
    "厌恶算法推荐": ["厌恶算法推荐", "反抗算法"],
    "精致品质生活": ["精致品质生活", "精致品质", "老钱/静奢"],
    "凑单退单高手": ["凑单退单高手", "凑单后立刻退", "为了满减计算到最优"],
    "理性比价/精明型": ["理性比价/精明型", "理性比价", "精明型", "参数党", "口碑党"],
    "为情绪价值买单": ["为情绪价值买单", "体验消费/享受型", "冲动消费/随性型"],
    "极简社交": ["极简社交", "极简社交（极少互动）", "围观潜水型"],
    "私域社群活跃者": ["私域社群活跃者", "私域社群活跃者（微信群/知识星球）"],
    "超前消费/信贷型": ["超前消费/信贷型", "花呗/白条/先用后付", "分期付款"],
    "本土主义/国潮信仰": ["本土主义/国潮信仰", "国潮信仰", "传统复兴/国学热"],
    "全球化/世界公民": ["全球化/世界公民", "文化混搭/无边界"],
    "量入为出/储蓄型": ["量入为出/储蓄型", "储蓄型"],
    "躺平/低欲望": ["躺平/低欲望", "躺平", "低欲望", "45度青年（想卷卷不动，想躺躺不平）"],
    "内卷/奋斗": ["内卷/奋斗", "内卷", "奋斗", "事业成就"],
}


def _weighted_choice(
    options: list[str], weights: list[float], rng: random.Random | None = None
) -> str:
    """Return a single option sampled according to the given weights."""
    if rng is None:
        return random.choices(options, weights=weights, k=1)[0]
    return rng.choices(options, weights=weights, k=1)[0]


def _sample_anxieties(life_stage: str, rng: random.Random) -> list[str]:
    """Sample 1-2 anxiety labels appropriate for the given life stage."""
    pool = LIFE_STAGE_ANXIETY_MAP.get(life_stage, ["同辈压力"])
    n = rng.choices([1, 2], weights=[0.4, 0.6], k=1)[0]
    if len(pool) <= n:
        return pool[:]
    return rng.sample(pool, k=n)


def _sample_income_bracket(
    city_tier: str,
    life_stage: str,
    rng: random.Random,
) -> str:
    """Sample an income bracket conditioned on city tier and life stage."""
    # Start from city-tier-specific distribution.
    tier_weights = CITY_TIER_INCOME_MULTIPLIERS.get(city_tier, INCOME_BASE_WEIGHTS)
    weights = list(tier_weights)

    # Apply life-stage constraints.
    constraints = LIFE_STAGE_INCOME_CONSTRAINTS.get(life_stage, {})
    max_idx = constraints.get("max_bracket_index")
    bias = constraints.get("bias")

    if max_idx is not None:
        # Zero out everything above the max allowed bracket.
        for i in range(max_idx + 1, len(weights)):
            weights[i] = 0.0

    if bias == "low":
        for i in range(len(weights)):
            weights[i] *= 1.0 + (len(weights) - i) * 0.15
    elif bias == "low_mid":
        for i in range(len(weights)):
            weights[i] *= 1.0 + abs(i - 2) * -0.10
    elif bias == "mid_high":
        for i in range(len(weights)):
            weights[i] *= 1.0 + i * 0.12

    total = sum(weights)
    if total == 0:
        weights = list(INCOME_BASE_WEIGHTS)
        total = sum(weights)
    weights = [w / total for w in weights]

    return _weighted_choice(INCOME_BRACKETS, weights, rng=rng)


class SeedGenerator:
    """Generates SeedConfig objects for virtual consumer personas.

    The generator performs weighted sampling across life stages, city tiers,
    and income brackets, matches anxiety labels to the sampled life stage,
    and computes tension scores based on contradictory tag combinations.
    """

    def __init__(self, seed: int | None = None) -> None:
        """Initialize the generator with an optional random seed.

        Args:
            seed: Optional integer seed for reproducible generation.
        """
        self._rng = random.Random(seed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_seed(self) -> SeedConfig:
        """Generate a single consumer seed configuration.

        Returns:
            A SeedConfig containing life_stage, anxieties, income_bracket,
            city_tier, tension_score, and tension_pairs.
        """
        life_stage = _weighted_choice(LIFE_STAGES, LIFE_STAGE_WEIGHTS, rng=self._rng)
        city_tier = _weighted_choice(CITY_TIERS, CITY_TIER_WEIGHTS, rng=self._rng)
        anxieties = _sample_anxieties(life_stage, self._rng)
        income_bracket = _sample_income_bracket(city_tier, life_stage, self._rng)

        # Build a preliminary tag set for tension detection.
        tags: set[str] = set(anxieties)
        tags.add(life_stage)
        tags.add(city_tier)
        tags.add(income_bracket)

        # Add a few behavioural tags so that tension detection has
        # something to work with beyond the skeleton triad.
        extra_tags = self._sample_extra_tags(life_stage, income_bracket)
        tags.update(extra_tags.values())

        tension_pairs = self.calculate_tension(tags)
        tension_score = self._aggregate_tension(tension_pairs)

        return SeedConfig(
            life_stage=life_stage,
            anxieties=anxieties,
            income_bracket=income_bracket,
            city_tier=city_tier,
            tension_score=tension_score,
            tension_pairs=tension_pairs,
            extra_tags=extra_tags,
        )

    def calculate_tension(self, tags: set[str]) -> list[TensionPair]:
        """Detect contradictory tag combinations and compute tension values.

        The method scans the provided tags against predefined tension
        definitions.  A match is detected when both sides of a tension
        definition are present (either directly or via aliases).

        Args:
            tags: A set of tag strings sampled for the consumer.

        Returns:
            A list of TensionPair objects, one per detected contradiction.
        """
        pairs: list[TensionPair] = []
        tag_list = list(tags)

        for tag_a_def, tag_b_def, base_tension, narrative in TENSION_DEFINITIONS:
            aliases_a = TAG_ALIASES.get(tag_a_def, [tag_a_def])
            aliases_b = TAG_ALIASES.get(tag_b_def, [tag_b_def])

            matched_a = any(a in tag_list for a in aliases_a)
            matched_b = any(b in tag_list for b in aliases_b)

            if matched_a and matched_b:
                # Slight randomisation so identical tag sets don't always
                # yield the exact same tension value.
                jitter = self._rng.uniform(-0.05, 0.05)
                tension_value = max(0.0, min(1.0, base_tension + jitter))
                pairs.append(
                    TensionPair(
                        tag_a=tag_a_def,
                        tag_b=tag_b_def,
                        tension_value=round(tension_value, 3),
                        narrative=narrative,
                    )
                )

        return pairs

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _aggregate_tension(self, pairs: list[TensionPair]) -> float:
        """Compute an overall tension score from a list of tension pairs.

        Uses a saturating sum so that many weak tensions don't unboundedly
        inflate the score beyond 1.0.
        """
        if not pairs:
            return 0.0
        raw = sum(p.tension_value for p in pairs)
        # Saturating formula: 1 - exp(-raw) maps [0, inf) -> [0, 1)
        score = 1.0 - 2.718281828459045 ** (-raw)
        return round(score, 3)

    def _sample_extra_tags(
        self, life_stage: str, income_bracket: str
    ) -> dict[str, Any]:
        """Sample a small number of behavioural / attitudinal tags.

        These tags enrich the seed and increase the chance of hitting
        predefined tension pairs.
        """
        extra: dict[str, Any] = {}

        # Lifestyle attitude pool.
        lifestyle_pool = [
            "精致品质",
            "简约质朴",
            "科技极客",
            "实用至上",
            "极简主义/断舍离",
            "躺平/低欲望",
            "内卷/奋斗",
            "朋克养生",
        ]
        extra["生活态度"] = self._rng.choice(lifestyle_pool)

        # Consumption concept pool.
        consumption_pool = [
            "量入为出/储蓄型",
            "超前消费/信贷型",
            "体验消费/享受型",
            "理性比价/精明型",
            "冲动消费/随性型",
            "反消费主义/极简消费",
        ]
        extra["消费观念"] = self._rng.choice(consumption_pool)

        # Social identity pool.
        social_pool = [
            "极简社交",
            "私域社群活跃者",
            "社交活跃型",
            "围观潜水型",
        ]
        extra["社交方式"] = self._rng.choice(social_pool)

        # Add an income-derived tag for tension detection.
        # Map bracket to a coarse "high / mid / low" tag.
        high_income_brackets = {"30-50万元", "50-100万元", "100万元以上"}
        if income_bracket in high_income_brackets:
            extra["收入标签"] = "高收入"
        elif income_bracket in {"15-30万元"}:
            extra["收入标签"] = "中高收入"
        else:
            extra["收入标签"] = "普通收入"

        # Life-stage derived tag for tension detection.
        if "退休" in life_stage:
            extra["人生阶段标签"] = "退休生活"
        elif "学生" in life_stage:
            extra["人生阶段标签"] = "学生"
        elif "职场" in life_stage:
            extra["人生阶段标签"] = "职场新人"
        else:
            extra["人生阶段标签"] = life_stage

        return extra
