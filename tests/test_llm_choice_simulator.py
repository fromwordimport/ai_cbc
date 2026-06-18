"""Tests for LLM-based CBC choice simulator."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

from dataclasses import dataclass
from typing import Any

import numpy as np
import pytest

from aicbc.core.simulation.llm_choice_simulator import (
    LLMChoiceSimulator,
    _build_choice_prompt,
    _build_system_prompt,
    _call_llm_for_choice,
)
from aicbc.questionnaire.models import (
    Alternative,
    CBCQuestionnaire,
    ChoiceSet,
    DesignParameters,
)
from tests.test_cbc_choice_simulator import _make_persona, _make_test_attributes


@dataclass
class _MockLLMResponse:
    content: str
    estimated_cost_usd: float = 0.001


class _MockLLMClient:
    """Mock LLM client that returns pre-configured responses."""

    def __init__(self, responses: list[dict[str, Any]] | None = None) -> None:
        self.responses = responses or []
        self.call_count = 0

    def generate(self, **kwargs: Any) -> _MockLLMResponse:
        if self.call_count < len(self.responses):
            resp = self.responses[self.call_count]
            self.call_count += 1
            return _MockLLMResponse(
                content=resp["content"],
                estimated_cost_usd=resp.get("cost", 0.001),
            )
        self.call_count += 1
        return _MockLLMResponse(
            content='{"chosen_alt_index": 0, "reasoning": "mock", "confidence": 0.8}',
            estimated_cost_usd=0.001,
        )


@pytest.fixture
def simple_questionnaire():
    """Return a manually constructed questionnaire with 3 choice sets."""
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


class TestBuildSystemPrompt:
    """Tests for _build_system_prompt."""

    def test_contains_persona_info(self) -> None:
        persona = _make_persona()
        prompt = _build_system_prompt(persona)
        assert "年龄" in prompt
        assert persona.layer1_demographics.age in prompt
        assert "价格敏感度" in prompt
        assert "矛盾张力" in prompt

    def test_contains_behavior_rules(self) -> None:
        persona = _make_persona()
        prompt = _build_system_prompt(persona)
        assert "凭直觉" in prompt
        assert "不是计算最优解" in prompt


class TestBuildChoicePrompt:
    """Tests for _build_choice_prompt."""

    def test_contains_alternatives(self) -> None:
        attrs = _make_test_attributes()
        cs = ChoiceSet(
            choice_set_id=1,
            alternatives=[
                Alternative(alt_index=0, attributes={"price": 100, "brand": "A"}),
                Alternative(alt_index=1, attributes={"price": 200, "brand": "B"}),
            ],
        )
        prompt = _build_choice_prompt(cs, attrs)
        assert "选项A" in prompt
        assert "选项B" in prompt
        assert "100" in prompt
        assert "200" in prompt
        assert "chosen_alt_index" in prompt

    def test_json_example_in_prompt(self) -> None:
        attrs = _make_test_attributes()
        cs = ChoiceSet(
            choice_set_id=1,
            alternatives=[
                Alternative(alt_index=0, attributes={"price": 100, "brand": "A"}),
            ],
        )
        prompt = _build_choice_prompt(cs, attrs)
        assert "reasoning" in prompt
        assert "confidence" in prompt
        assert "emotion" in prompt


class TestCallLLMForChoice:
    """Tests for _call_llm_for_choice."""

    def test_successful_choice(self) -> None:
        client = _MockLLMClient(
            [
                {"content": '{"chosen_alt_index": 1, "reasoning": " cheaper", "confidence": 0.9}'},
            ]
        )
        chosen, reasoning, conf, _emotion, cost = _call_llm_for_choice(
            llm=client,
            model=None,
            system_prompt="sys",
            user_prompt="user",
            n_alternatives=2,
            rng=np.random.default_rng(42),
        )
        assert chosen == 1
        assert reasoning == " cheaper"
        assert conf == 0.9
        assert cost == 0.001

    def test_invalid_index_fallback(self) -> None:
        client = _MockLLMClient(
            [
                {"content": '{"chosen_alt_index": 5, "reasoning": "bad", "confidence": 0.5}'},
            ]
        )
        chosen, reasoning, conf, _emotion, cost = _call_llm_for_choice(
            llm=client,
            model=None,
            system_prompt="sys",
            user_prompt="user",
            n_alternatives=2,
            rng=np.random.default_rng(42),
        )
        assert chosen in {0, 1}
        assert "无效索引" in reasoning
        assert cost == 0.001

    def test_llm_failure_fallback(self) -> None:
        class FailingClient:
            def generate(self, **kwargs: Any) -> None:
                raise RuntimeError("API down")

        chosen, reasoning, conf, _emotion, cost = _call_llm_for_choice(
            llm=FailingClient(),
            model=None,
            system_prompt="sys",
            user_prompt="user",
            n_alternatives=2,
            rng=np.random.default_rng(42),
        )
        assert chosen is None
        assert "失败" in reasoning
        assert cost == 0.0

    def test_json_parse_failure(self) -> None:
        client = _MockLLMClient(
            [
                {"content": "not json at all"},
            ]
        )
        chosen, reasoning, conf, _emotion, cost = _call_llm_for_choice(
            llm=client,
            model=None,
            system_prompt="sys",
            user_prompt="user",
            n_alternatives=2,
            rng=np.random.default_rng(42),
        )
        assert chosen is None
        assert cost == 0.001

    def test_missing_confidence_defaults(self) -> None:
        client = _MockLLMClient(
            [
                {"content": '{"chosen_alt_index": 0, "reasoning": "ok"}'},
            ]
        )
        chosen, _reasoning, conf, _emotion, _cost = _call_llm_for_choice(
            llm=client,
            model=None,
            system_prompt="sys",
            user_prompt="user",
            n_alternatives=2,
            rng=np.random.default_rng(42),
        )
        assert chosen == 0
        assert conf == 0.5


class TestLLMChoiceSimulator:
    """Tests for LLMChoiceSimulator end-to-end."""

    def test_simulate_full_questionnaire(self, simple_questionnaire) -> None:
        attrs = _make_test_attributes()
        persona = _make_persona()

        client = _MockLLMClient(
            [
                {"content": '{"chosen_alt_index": 0, "reasoning": "r1", "confidence": 0.8}'},
                {"content": '{"chosen_alt_index": 0, "reasoning": "r2", "confidence": 0.7}'},
                {"content": '{"chosen_alt_index": 0, "reasoning": "r3", "confidence": 0.9}'},
            ]
        )

        simulator = LLMChoiceSimulator(attributes=attrs, llm_client=client)
        raw_dataset, persona_response = simulator.simulate(
            persona=persona,
            questionnaire=simple_questionnaire,
        )

        assert len(raw_dataset.choice_records) == 3
        assert len(persona_response.responses) == 3
        assert persona_response.completion_status == "COMPLETED"
        assert persona_response.cost_cny > 0
        assert client.call_count == 3

        for record in raw_dataset.choice_records:
            chosen_count = sum(1 for a in record.alternatives if a.chosen)
            assert chosen_count == 1
            chosen_alt = next(a for a in record.alternatives if a.chosen)
            assert chosen_alt.alt_index == 0

    def test_partial_completion_on_failure(self, simple_questionnaire) -> None:
        attrs = _make_test_attributes()
        persona = _make_persona()

        client = _MockLLMClient(
            [
                {"content": '{"chosen_alt_index": 0, "reasoning": "r1", "confidence": 0.8}'},
                {"content": "bad json"},
                {"content": '{"chosen_alt_index": 1, "reasoning": "r3", "confidence": 0.9}'},
            ]
        )

        simulator = LLMChoiceSimulator(attributes=attrs, llm_client=client)
        raw_dataset, persona_response = simulator.simulate(
            persona=persona,
            questionnaire=simple_questionnaire,
        )

        assert persona_response.completion_status == "PARTIAL"
        assert len(raw_dataset.choice_records) == 3
        assert client.call_count == 3

    def test_reasoning_in_response(self, simple_questionnaire) -> None:
        attrs = _make_test_attributes()
        persona = _make_persona()

        client = _MockLLMClient(
            [
                {"content": '{"chosen_alt_index": 0, "reasoning": "价格便宜", "confidence": 0.8}'},
                {"content": '{"chosen_alt_index": 1, "reasoning": "品牌好", "confidence": 0.7}'},
                {"content": '{"chosen_alt_index": 0, "reasoning": "综合不错", "confidence": 0.9}'},
            ]
        )

        simulator = LLMChoiceSimulator(attributes=attrs, llm_client=client)
        _raw_dataset, persona_response = simulator.simulate(
            persona=persona,
            questionnaire=simple_questionnaire,
        )

        assert persona_response.responses[0].reasoning == "价格便宜"
        assert persona_response.responses[1].reasoning == "品牌好"
        assert persona_response.responses[0].confidence == 0.8

    def test_seed_parameter_ignored(self, simple_questionnaire) -> None:
        """seed parameter is accepted for API compat but does not affect choices."""
        attrs = _make_test_attributes()
        persona = _make_persona()

        client = _MockLLMClient(
            [
                {"content": '{"chosen_alt_index": 0, "reasoning": "r", "confidence": 0.8}'},
                {"content": '{"chosen_alt_index": 0, "reasoning": "r", "confidence": 0.8}'},
                {"content": '{"chosen_alt_index": 0, "reasoning": "r", "confidence": 0.8}'},
            ]
        )

        simulator = LLMChoiceSimulator(attributes=attrs, llm_client=client)
        raw1, _resp1 = simulator.simulate(
            persona=persona,
            questionnaire=simple_questionnaire,
            seed=42,
        )
        # seed doesn't affect LLM calls, just accepted for compat
        assert len(raw1.choice_records) == 3
