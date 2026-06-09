"""Unit tests for SeedGenerator and SeedConfig."""

from __future__ import annotations

import pytest

from aicbc.core.models.seed_config import SeedConfig, TensionPair
from aicbc.generators.seed_generator import (
    CITY_TIERS,
    INCOME_BRACKETS,
    LIFE_STAGES,
    SeedGenerator,
    _sample_anxieties,
    _sample_income_bracket,
    _weighted_choice,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestWeightedChoice:
    """Tests for the _weighted_choice helper."""

    def test_returns_one_of_the_options(self) -> None:
        options = ["a", "b", "c"]
        weights = [0.5, 0.3, 0.2]
        result = _weighted_choice(options, weights)
        assert result in options

    def test_deterministic_with_zero_weight(self) -> None:
        options = ["a", "b"]
        weights = [1.0, 0.0]
        assert _weighted_choice(options, weights) == "a"


class TestSampleAnxieties:
    """Tests for anxiety label sampling."""

    def test_returns_known_anxieties_for_life_stage(self) -> None:
        import random

        rng = random.Random(42)
        anxieties = _sample_anxieties("学生", rng)
        assert len(anxieties) >= 1
        assert all(a in ["同辈压力", "身份迷茫/转型期"] for a in anxieties)

    def test_returns_fallback_for_unknown_stage(self) -> None:
        import random

        rng = random.Random(42)
        anxieties = _sample_anxieties("未知阶段", rng)
        assert anxieties == ["同辈压力"]

    def test_does_not_exceed_pool_size(self) -> None:
        import random

        rng = random.Random(42)
        # "学生" only has 2 anxieties defined.
        anxieties = _sample_anxieties("学生", rng)
        assert len(anxieties) <= 2


class TestSampleIncomeBracket:
    """Tests for income bracket sampling."""

    def test_returns_valid_bracket(self) -> None:
        import random

        rng = random.Random(42)
        bracket = _sample_income_bracket("一线城市", "初入职场单身", rng)
        assert bracket in INCOME_BRACKETS

    def test_student_capped_at_low_bracket(self) -> None:
        import random

        rng = random.Random(42)
        # Students should never exceed index 3 (8-15万元) because of the
        # max_bracket_index constraint.
        for _ in range(100):
            bracket = _sample_income_bracket("一线城市", "学生", rng)
            idx = INCOME_BRACKETS.index(bracket)
            assert idx <= 3, f"Student got unexpected bracket {bracket}"

    def test_city_tier_influences_distribution(self) -> None:
        import random

        rng = random.Random(42)
        # Tier-1 should produce higher brackets on average than county.
        tier1_samples = [
            _sample_income_bracket("一线城市", "中年空巢（子女独立）", rng)
            for _ in range(200)
        ]
        county_samples = [
            _sample_income_bracket("县城/乡镇", "中年空巢（子女独立）", rng)
            for _ in range(200)
        ]

        def mean_index(samples: list[str]) -> float:
            return sum(INCOME_BRACKETS.index(s) for s in samples) / len(samples)

        assert mean_index(tier1_samples) > mean_index(county_samples)


# ---------------------------------------------------------------------------
# SeedConfig model
# ---------------------------------------------------------------------------


class TestSeedConfig:
    """Tests for the SeedConfig Pydantic model."""

    def test_valid_construction(self) -> None:
        config = SeedConfig(
            life_stage="学生",
            anxieties=["同辈压力"],
            income_bracket="3-8万元",
            city_tier="二线城市",
            tension_score=0.5,
            tension_pairs=[
                TensionPair(
                    tag_a="高收入",
                    tag_b="极简主义",
                    tension_value=0.75,
                    narrative="test",
                )
            ],
        )
        assert config.life_stage == "学生"
        assert config.anxieties == ["同辈压力"]

    def test_tension_score_clamping(self) -> None:
        config = SeedConfig(
            life_stage="学生",
            anxieties=["同辈压力"],
            income_bracket="3-8万元",
            city_tier="二线城市",
            tension_score=1.5,
        )
        assert config.tension_score == 1.0

    def test_tension_score_negative_clamping(self) -> None:
        config = SeedConfig(
            life_stage="学生",
            anxieties=["同辈压力"],
            income_bracket="3-8万元",
            city_tier="二线城市",
            tension_score=-0.5,
        )
        assert config.tension_score == 0.0

    def test_anxiety_deduplication(self) -> None:
        config = SeedConfig(
            life_stage="学生",
            anxieties=["同辈压力", "同辈压力", "身份迷茫/转型期"],
            income_bracket="3-8万元",
            city_tier="二线城市",
        )
        assert config.anxieties == ["同辈压力", "身份迷茫/转型期"]

    def test_empty_anxieties_raises(self) -> None:
        with pytest.raises(ValueError):
            SeedConfig(
                life_stage="学生",
                anxieties=[],
                income_bracket="3-8万元",
                city_tier="二线城市",
            )

    def test_tension_pair_clamping(self) -> None:
        pair = TensionPair(
            tag_a="a",
            tag_b="b",
            tension_value=1.2,
        )
        assert pair.tension_value == 1.0


# ---------------------------------------------------------------------------
# SeedGenerator
# ---------------------------------------------------------------------------


class TestSeedGenerator:
    """Tests for the SeedGenerator class."""

    def test_generate_seed_returns_seed_config(self) -> None:
        gen = SeedGenerator(seed=42)
        seed = gen.generate_seed()
        assert isinstance(seed, SeedConfig)

    def test_seed_fields_populated(self) -> None:
        gen = SeedGenerator(seed=42)
        seed = gen.generate_seed()
        assert seed.life_stage in LIFE_STAGES
        assert seed.city_tier in CITY_TIERS
        assert seed.income_bracket in INCOME_BRACKETS
        assert len(seed.anxieties) >= 1
        assert all(isinstance(a, str) for a in seed.anxieties)

    def test_tension_score_in_range(self) -> None:
        gen = SeedGenerator(seed=42)
        for _ in range(50):
            seed = gen.generate_seed()
            assert 0.0 <= seed.tension_score <= 1.0

    def test_reproducibility_with_same_seed(self) -> None:
        gen1 = SeedGenerator(seed=123)
        gen2 = SeedGenerator(seed=123)
        s1 = gen1.generate_seed()
        s2 = gen2.generate_seed()
        assert s1.life_stage == s2.life_stage
        assert s1.city_tier == s2.city_tier
        assert s1.income_bracket == s2.income_bracket
        assert s1.anxieties == s2.anxieties

    def test_different_seeds_produce_different_results(self) -> None:
        gen1 = SeedGenerator(seed=1)
        gen2 = SeedGenerator(seed=2)
        s1 = gen1.generate_seed()
        s2 = gen2.generate_seed()
        # It is extremely unlikely that two different seeds produce
        # identical life_stage, city_tier, income_bracket, and anxieties.
        assert (
            s1.life_stage != s2.life_stage
            or s1.city_tier != s2.city_tier
            or s1.income_bracket != s2.income_bracket
            or s1.anxieties != s2.anxieties
        )

    def test_calculate_tension_detects_defined_pairs(self) -> None:
        gen = SeedGenerator(seed=42)
        tags = {"高收入", "极简主义", "精致品质生活", "凑单退单高手"}
        pairs = gen.calculate_tension(tags)
        tag_sets = {(p.tag_a, p.tag_b) for p in pairs}
        assert ("高收入", "极简主义") in tag_sets
        assert ("精致品质生活", "凑单退单高手") in tag_sets

    def test_calculate_tension_returns_empty_for_no_matches(self) -> None:
        gen = SeedGenerator(seed=42)
        tags = {"学生", "二线城市", "3-8万元"}
        pairs = gen.calculate_tension(tags)
        assert pairs == []

    def test_calculate_tension_uses_aliases(self) -> None:
        gen = SeedGenerator(seed=42)
        # "30-50万元" is an alias for "高收入".
        tags = {"30-50万元", "极简主义/断舍离"}
        pairs = gen.calculate_tension(tags)
        assert any(p.tag_a == "高收入" and p.tag_b == "极简主义" for p in pairs)

    def test_tension_values_in_range(self) -> None:
        gen = SeedGenerator(seed=42)
        tags = {"高收入", "极简主义", "数码极客", "厌恶算法推荐"}
        pairs = gen.calculate_tension(tags)
        for p in pairs:
            assert 0.0 <= p.tension_value <= 1.0

    def test_extra_tags_present(self) -> None:
        gen = SeedGenerator(seed=42)
        seed = gen.generate_seed()
        assert "生活态度" in seed.extra_tags
        assert "消费观念" in seed.extra_tags
        assert "社交方式" in seed.extra_tags
        assert "收入标签" in seed.extra_tags

    def test_batch_generation_coverage(self) -> None:
        """Generate a large batch and assert basic distributional coverage."""
        gen = SeedGenerator(seed=0)
        seeds = [gen.generate_seed() for _ in range(200)]

        life_stages = {s.life_stage for s in seeds}
        city_tiers = {s.city_tier for s in seeds}
        income_brackets = {s.income_bracket for s in seeds}

        # We should see at least a few different values for each dimension.
        assert len(life_stages) >= 3
        assert len(city_tiers) >= 3
        assert len(income_brackets) >= 3

        # At least some seeds should have tension (because extra_tags inject
        # behavioural tags that frequently hit predefined tension pairs).
        tension_seeds = [s for s in seeds if s.tension_score > 0]
        assert len(tension_seeds) >= 10
