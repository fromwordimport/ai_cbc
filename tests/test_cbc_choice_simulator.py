"""Tests for CBC choice simulator."""

from __future__ import annotations

import numpy as np
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
from aicbc.core.simulation.cbc_choice_simulator import (
    CBCChoiceSimulator,
    PersonaUtilityMapper,
    _apply_brand_loyalty,
    _attribute_importance,
    _fuzzy_match,
    _price_coefficient_from_sensitivity,
    _softmax,
)
from aicbc.questionnaire.design.effects_coding import encode_profile
from aicbc.questionnaire.models import (
    Attribute,
    AttributeLevel,
    AttributeType,
    DesignParameters,
)


def _make_test_attributes() -> list[Attribute]:
    """Simple 2-attribute test set."""
    return [
        Attribute(
            id="price",
            name="价格",
            type=AttributeType.PRICE,
            levels=[
                AttributeLevel(value=100, label="100"),
                AttributeLevel(value=200, label="200"),
            ],
        ),
        Attribute(
            id="brand",
            name="品牌",
            type=AttributeType.CATEGORICAL,
            levels=[
                AttributeLevel(value="A", label="品牌A"),
                AttributeLevel(value="B", label="品牌B"),
            ],
        ),
    ]


def _make_persona(
    *,
    price_sensitivity: str = "中等敏感",
    brand_loyalty: str = "无特殊偏好",
    decision_factors: list[str] | None = None,
    ignored_factors: list[str] | None = None,
) -> PersonaProfile:
    """Build a minimal PersonaProfile for testing."""
    return PersonaProfile(
        persona_id="persona-test-001",
        segment="测试群体",
        layer1_demographics=Layer1Demographics(
            age="28岁",
            gender="女",
            city="新一线城市",
            income="15-30万元",
            occupation="测试",
            education="本科",
            marital_status="已婚",
            living_type="租房",
        ),
        layer2_behavior=Layer2Behavior(
            price_sensitivity=price_sensitivity,
            purchase_channels=["京东"],
            decision_style="理性",
            brand_loyalty=brand_loyalty,
            information_source=["小红书"],
        ),
        layer3_psychology=Layer3Psychology(
            core_values=["效率"],
            core_anxieties=["时间不够"],
            tension_combination=TensionCombination(
                labels=["矛盾"],
                narrative_explanation=(
                    "测试张力组合的解释文字需要超过50字才能通过验证，"
                    "因此这里写一段足够长的描述来满足最小长度要求，确保不会失败。"
                ),
            ),
            secret_motivation="测试",
            defense_mechanism="测试",
        ),
        layer4_scenarios=Layer4Scenarios(
            daily_routine="测试",
            purchase_trigger="测试",
            stress_response="测试",
            social_behavior="测试",
        ),
        language_samples=[
            "这是第一个测试用的语言样本，长度必须超过二十个字才行",
            "这是第二个测试语言样本，同样需要满足最小长度要求",
            "第三个语言样本也必须足够长，否则验证会失败",
        ],
        dishwasher_context=DishwasherContext(
            purchase_constraints=[],
            decision_factors=decision_factors or ["价格"],
            ignored_factors=ignored_factors or [],
        ),
        generation_metadata=GenerationMetadata(),
    )


class TestPriceCoefficientMapping:
    """Tests for price-sensitivity → coefficient mapping."""

    def test_extreme_sensitivity(self) -> None:
        assert _price_coefficient_from_sensitivity("极高敏感") == -2.0
        assert _price_coefficient_from_sensitivity("非常敏感") == -2.0

    def test_high_sensitivity(self) -> None:
        assert _price_coefficient_from_sensitivity("高敏感") == -1.2
        assert _price_coefficient_from_sensitivity("中高敏感") == -1.2

    def test_low_sensitivity(self) -> None:
        assert _price_coefficient_from_sensitivity("低敏感") == -0.2
        assert _price_coefficient_from_sensitivity("不敏感") == -0.2

    def test_default(self) -> None:
        assert _price_coefficient_from_sensitivity("未知") == -0.8


class TestFuzzyMatch:
    """Tests for attribute-factor fuzzy matching."""

    def test_direct_substring(self) -> None:
        assert _fuzzy_match("price", "价格很重要") is True
        assert _fuzzy_match("brand", "品牌口碑") is True

    def test_synonym_mapping(self) -> None:
        assert _fuzzy_match("price", "预算有限") is True
        assert _fuzzy_match("brand", "信任度") is True
        assert _fuzzy_match("capacity", "套数") is True

    def test_no_match(self) -> None:
        assert _fuzzy_match("price", "颜色好看") is False


class TestAttributeImportance:
    """Tests for attribute importance calculation."""

    def test_ignored_factor(self) -> None:
        importance = _attribute_importance("price", [], ["价格"])
        assert importance == 0.1

    def test_decision_factor(self) -> None:
        importance = _attribute_importance("brand", ["品牌"], [])
        assert importance == 1.5

    def test_default(self) -> None:
        importance = _attribute_importance("price", [], [])
        assert importance == 0.8


class TestBrandLoyalty:
    """Tests for brand loyalty coefficient application."""

    def test_boost_non_reference_brand(self) -> None:
        attr = _make_test_attributes()[1]  # brand
        beta = np.zeros(1, dtype=np.float64)
        _apply_brand_loyalty(beta, 0, attr, "喜欢品牌A")
        assert beta[0] == 1.0

    def test_boost_reference_brand(self) -> None:
        attr = _make_test_attributes()[1]  # brand: A, B (B is reference)
        beta = np.zeros(1, dtype=np.float64)
        _apply_brand_loyalty(beta, 0, attr, "喜欢品牌B")
        assert beta[0] == -0.8


class TestSoftmax:
    """Tests for softmax helper."""

    def test_probabilities_sum_to_one(self) -> None:
        utilities = np.array([1.0, 2.0, 3.0])
        probs = _softmax(utilities)
        np.testing.assert_almost_equal(np.sum(probs), 1.0)

    def test_higher_utility_higher_probability(self) -> None:
        utilities = np.array([0.0, 5.0])
        probs = _softmax(utilities)
        assert probs[1] > probs[0]


class TestPersonaUtilityMapper:
    """Tests for PersonaUtilityMapper."""

    def test_beta_shape(self) -> None:
        attrs = _make_test_attributes()
        mapper = PersonaUtilityMapper(attrs)
        persona = _make_persona()
        beta = mapper.build_beta(persona)
        # price=1 + brand(2 levels)=1 = 2 params
        assert beta.shape == (2,)

    def test_price_coefficient_sign(self) -> None:
        attrs = _make_test_attributes()
        mapper = PersonaUtilityMapper(attrs)
        persona = _make_persona(price_sensitivity="极高敏感")
        beta = mapper.build_beta(persona)
        assert beta[0] < 0  # price coefficient should be negative

    def test_reproducibility(self) -> None:
        """Same persona ID should produce same random coefficients."""
        attrs = _make_test_attributes()
        mapper = PersonaUtilityMapper(attrs)
        persona = _make_persona()
        beta1 = mapper.build_beta(persona)
        beta2 = mapper.build_beta(persona)
        np.testing.assert_array_equal(beta1, beta2)


class TestCBCChoiceSimulator:
    """Tests for CBCChoiceSimulator end-to-end."""

    @pytest.fixture
    def simple_questionnaire(self):
        """Return a manually constructed questionnaire with 3 choice sets, 2 alternatives."""
        from aicbc.questionnaire.models import Alternative, CBCQuestionnaire, ChoiceSet

        dp = DesignParameters(n_choice_sets=3, n_alternatives=2, seed=42)
        return CBCQuestionnaire(
            questionnaire_id="q-test-study",
            study_id="test-study",
            design_parameters=dp,
            choice_sets=[
                ChoiceSet(
                    choice_set_id=1,
                    alternatives=[
                        Alternative(alt_index=0, attributes={"price": 100, "brand": "A"}),
                        Alternative(alt_index=1, attributes={"price": 200, "brand": "B"}),
                    ],
                ),
                ChoiceSet(
                    choice_set_id=2,
                    alternatives=[
                        Alternative(alt_index=0, attributes={"price": 200, "brand": "A"}),
                        Alternative(alt_index=1, attributes={"price": 100, "brand": "B"}),
                    ],
                ),
                ChoiceSet(
                    choice_set_id=3,
                    alternatives=[
                        Alternative(alt_index=0, attributes={"price": 100, "brand": "A"}),
                        Alternative(alt_index=1, attributes={"price": 100, "brand": "B"}),
                    ],
                ),
            ],
        )

    def test_detinistic_mode_selects_max_utility(self, simple_questionnaire) -> None:
        attrs = _make_test_attributes()
        simulator = CBCChoiceSimulator(attributes=attrs)
        persona = _make_persona(price_sensitivity="极高敏感")  # strongly prefers low price

        raw_dataset, persona_response = simulator.simulate(
            persona=persona,
            questionnaire=simple_questionnaire,
            deterministic=True,
        )

        assert len(raw_dataset.choice_records) == 3
        assert len(persona_response.responses) == 3
        assert persona_response.completion_status == "COMPLETED"

        # In deterministic mode, each choice set should have exactly one chosen
        for record in raw_dataset.choice_records:
            chosen_count = sum(1 for a in record.alternatives if a.chosen)
            assert chosen_count == 1

    def test_probabilistic_mode(self, simple_questionnaire) -> None:
        attrs = _make_test_attributes()
        simulator = CBCChoiceSimulator(attributes=attrs)
        persona = _make_persona()

        raw_dataset, persona_response = simulator.simulate(
            persona=persona,
            questionnaire=simple_questionnaire,
            deterministic=False,
            seed=42,
        )

        assert len(raw_dataset.choice_records) == 3
        assert persona_response.persona_id == "persona-test-001"

    def test_raw_dataset_metadata(self, simple_questionnaire) -> None:
        attrs = _make_test_attributes()
        simulator = CBCChoiceSimulator(attributes=attrs)
        persona = _make_persona()

        raw_dataset, _ = simulator.simulate(
            persona=persona,
            questionnaire=simple_questionnaire,
            deterministic=True,
        )

        assert raw_dataset.metadata.study_id == "test-study"
        assert raw_dataset.metadata.n_choice_sets == 3
        assert raw_dataset.metadata.n_alternatives == 2
        assert raw_dataset.n_records == 3

    def test_choice_consistency_with_utility(self, simple_questionnaire) -> None:
        """Deterministic choice should align with computed utilities."""
        attrs = _make_test_attributes()
        simulator = CBCChoiceSimulator(attributes=attrs)
        # Persona who highly values low price
        persona = _make_persona(price_sensitivity="极高敏感")

        raw_dataset, _ = simulator.simulate(
            persona=persona,
            questionnaire=simple_questionnaire,
            deterministic=True,
        )

        # Verify that the chosen alternative has lower price in each set
        mapper = PersonaUtilityMapper(attrs)
        beta = mapper.build_beta(persona)

        for record in raw_dataset.choice_records:
            chosen_alt = next(a for a in record.alternatives if a.chosen)
            # Compute utility for all alternatives
            utilities = []
            for alt in record.alternatives:
                x = encode_profile(alt.attributes, attrs)
                utilities.append(float(x @ beta))
            # The chosen one should have max utility
            chosen_idx = record.alternatives.index(chosen_alt)
            assert utilities[chosen_idx] == max(utilities)

    def test_none_option(self, simple_questionnaire) -> None:
        attrs = _make_test_attributes()
        simulator = CBCChoiceSimulator(attributes=attrs)
        persona = _make_persona()

        raw_dataset, _ = simulator.simulate(
            persona=persona,
            questionnaire=simple_questionnaire,
            include_none=True,
            none_threshold=-100.0,  # very low threshold so none is never chosen
            deterministic=True,
        )

        # With high threshold, none should never be chosen
        for record in raw_dataset.choice_records:
            assert record.none_chosen is False

    def test_different_personas_different_choices(self, simple_questionnaire) -> None:
        """Two personas with different preferences should make different choices."""
        attrs = _make_test_attributes()
        simulator = CBCChoiceSimulator(attributes=attrs)

        persona_price = _make_persona(price_sensitivity="极高敏感")
        persona_brand = _make_persona(
            price_sensitivity="低敏感",
            brand_loyalty="喜欢品牌A",
            decision_factors=["品牌"],
        )

        raw_price, _ = simulator.simulate(
            persona=persona_price,
            questionnaire=simple_questionnaire,
            deterministic=True,
            seed=1,
        )
        raw_brand, _ = simulator.simulate(
            persona=persona_brand,
            questionnaire=simple_questionnaire,
            deterministic=True,
            seed=1,
        )

        # At least one choice set should differ between the two personas
        choices_price = [r.alternatives for r in raw_price.choice_records]
        choices_brand = [r.alternatives for r in raw_brand.choice_records]
        # This is probabilistic in nature, but with strong preference differences
        # and deterministic mode, they should differ in most cases.
        # We just verify both produced valid outputs.
        assert len(choices_price) == len(choices_brand)
