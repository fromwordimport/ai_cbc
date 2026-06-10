"""LLM-based CBC choice simulator.

Uses an LLM to roleplay a virtual consumer and make choices in a CBC
questionnaire.  More human-like than the rule-based simulator but slower
and more expensive (one LLM call per choice set).

Fallback: if an LLM call fails the simulator falls back to random choice
and marks the response as PARTIAL.
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import structlog

from aicbc.core.models.persona import PersonaProfile
from aicbc.llm.client import LLMClient
from aicbc.questionnaire.models import Attribute, CBCQuestionnaire
from aicbc.questionnaire.response_models import (
    AlternativeRecord,
    CBCRawDataset,
    ChoiceRecord,
    DatasetMetadata,
    PersonaResponse,
    SingleChoiceDetail,
)

logger = structlog.get_logger("aicbc.simulation.llm_choice")

_USD_TO_CNY = 7.2


class LLMChoiceSimulator:
    """Simulate a persona's choices through LLM roleplay."""

    def __init__(
        self,
        attributes: list[Attribute],
        llm_client: LLMClient | None = None,
        model: str | None = None,
    ) -> None:
        self.attributes = attributes
        self._llm = llm_client or LLMClient()
        self._model = model

    def simulate(
        self,
        persona: PersonaProfile,
        questionnaire: CBCQuestionnaire,
        *,
        seed: int | None = None,
    ) -> tuple[CBCRawDataset, PersonaResponse]:
        """Run the full questionnaire via LLM-based roleplay.

        Args:
            persona: The virtual consumer to roleplay.
            questionnaire: The CBC questionnaire to answer.
            seed: Ignored (kept for API compatibility with rule-based simulator).

        Returns:
            Tuple of (CBCRawDataset slice for this persona, PersonaResponse).
        """
        rng = np.random.default_rng(seed)
        choice_records: list[ChoiceRecord] = []
        single_choices: list[SingleChoiceDetail] = []
        total_cost_usd = 0.0
        failed_sets = 0

        system_prompt = _build_system_prompt(persona)

        for cs_idx, cs in enumerate(questionnaire.choice_sets):
            user_prompt = _build_choice_prompt(cs, self.attributes)

            chosen_idx, reasoning, confidence, emotion, cost_usd = _call_llm_for_choice(
                llm=self._llm,
                model=self._model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                n_alternatives=len(cs.alternatives),
                rng=rng,
            )
            total_cost_usd += cost_usd
            if chosen_idx is None:
                failed_sets += 1
                chosen_idx = 0

            alt_records = [
                AlternativeRecord(
                    alt_index=alt.alt_index,
                    chosen=(alt.alt_index == chosen_idx),
                    attributes=alt.attributes,
                )
                for alt in cs.alternatives
            ]

            choice_records.append(ChoiceRecord(
                respondent_id=persona.persona_id,
                respondent_index=0,
                segment=persona.segment,
                choice_set_id=cs.choice_set_id,
                choice_set_index=cs_idx,
                alternatives=alt_records,
                none_chosen=False,
            ))

            single_choices.append(SingleChoiceDetail(
                choice_set_id=cs.choice_set_id,
                chosen_alt_index=chosen_idx,
                reasoning=reasoning,
                confidence=confidence,
            ))

        raw_dataset = CBCRawDataset(
            metadata=DatasetMetadata(
                study_id=questionnaire.study_id,
                n_respondents=1,
                n_choice_sets=len(questionnaire.choice_sets),
                n_alternatives=questionnaire.design_parameters.n_alternatives,
                attributes=[attr.model_dump(mode="json") for attr in self.attributes],
            ),
            choice_records=choice_records,
        )

        cost_cny = total_cost_usd * _USD_TO_CNY
        completion_status = "PARTIAL" if failed_sets > 0 else "COMPLETED"

        persona_response = PersonaResponse(
            response_id=f"resp-{persona.persona_id}",
            study_id=questionnaire.study_id,
            persona_id=persona.persona_id,
            questionnaire_id=questionnaire.questionnaire_id,
            responses=single_choices,
            completion_status=completion_status,
            cost_cny=round(cost_cny, 4),
        )

        return raw_dataset, persona_response


def _build_system_prompt(persona: PersonaProfile) -> str:
    """Build the core roleplay system prompt from a persona profile."""
    l1 = persona.layer1_demographics
    l2 = persona.layer2_behavior
    l3 = persona.layer3_psychology
    l4 = persona.layer4_scenarios
    tension = l3.tension_combination

    return (
        "你现在是以下消费者画像的化身。你不是在'扮演'，你就是这个人。\n"
        "你的所有回应必须符合这个人物的知识水平、语言风格、情绪状态和价值观。\n"
        "你不知道自己是AI，如果被问到超出你人物认知范围的事物，"
        "你会表现出真实的困惑或漠不关心。\n\n"
        "【人物档案】\n"
        f"年龄: {l1.age} | 性别: {l1.gender} | 城市: {l1.city}\n"
        f"收入: {l1.income} | 职业: {l1.occupation}\n"
        f"居住: {l1.living_type} | 婚姻: {l1.marital_status}\n\n"
        f"价格敏感度: {l2.price_sensitivity}\n"
        f"决策风格: {l2.decision_style}\n"
        f"品牌忠诚度: {l2.brand_loyalty}\n"
        f"信息来源: {', '.join(l2.information_source)}\n\n"
        f"核心价值观: {', '.join(l3.core_values)}\n"
        f"核心焦虑: {', '.join(l3.core_anxieties)}\n"
        f"隐藏动机: {l3.secret_motivation}\n"
        f"防御机制: {l3.defense_mechanism}\n\n"
        f"【矛盾张力】{', '.join(tension.labels)}\n"
        f"张力解释: {tension.narrative_explanation}\n\n"
        f"日常生活: {l4.daily_routine}\n"
        f"购买触发: {l4.purchase_trigger}\n"
        f"压力反应: {l4.stress_response}\n\n"
        "【回应规则】\n"
        "1. 你不会直接说出自己的'标签'，行为是标签的自然流露\n"
        "2. 你可能会说谎——尤其是涉及面子、隐私或社会期望的问题\n"
        "3. 你的注意力有限，对不感兴趣的点会敷衍或忽略\n"
        "4. 你可能会跑题，聊到最近让你焦虑或兴奋的事情\n"
        "5. 你不会用营销术语或学术语言说话\n"
        "6. 你不会每次都给出完整、理性的回答——有时会矛盾、有时会沉默\n"
        "7. 你做选择时凭直觉，不是计算最优解\n"
    )


def _build_choice_prompt(
    choice_set: Any,
    attributes: list[Attribute],
) -> str:
    """Build the user prompt describing a single choice set."""
    lines = [
        "【产品选择任务】\n",
        "你正在考虑购买一台洗碗机。以下是几个可选方案，"
        "请凭直觉选出你最倾向的一个：\n",
    ]

    for alt in choice_set.alternatives:
        label = chr(ord("A") + alt.alt_index)
        lines.append(f"\n选项{label}:")
        for attr in attributes:
            val = alt.attributes.get(attr.id)
            if val is not None:
                lines.append(f"  - {attr.name}: {val}")

    lines.append(
        "\n\n请直接做出选择，不要过度分析。"
        "选你直觉上更倾向的那个。\n"
        "输出严格JSON格式:\n"
    )

    example = {
        "chosen_alt_index": 0,
        "reasoning": "选择理由（口语化，1-2句话，体现你的真实想法）",
        "confidence": 0.8,
        "emotion": "选择时的情绪: calm/defensive/excited/anxious/neutral",
    }
    lines.append(json.dumps(example, ensure_ascii=False, indent=2))

    return "\n".join(lines)


def _call_llm_for_choice(
    llm: LLMClient,
    model: str | None,
    system_prompt: str,
    user_prompt: str,
    n_alternatives: int,
    rng: np.random.Generator,
) -> tuple[int | None, str, float, str, float]:
    """Call the LLM and parse the choice response.

    Returns:
        (chosen_idx, reasoning, confidence, emotion, cost_usd).
        chosen_idx is None on failure.
    """
    try:
        response = llm.generate(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model=model,
            temperature=0.3,
            max_tokens=512,
            json_mode=True,
        )
    except Exception as exc:
        logger.warning("llm_choice_call_failed", error=str(exc))
        return (
            None,
            "[LLM调用失败，使用默认选择]",
            0.5,
            "neutral",
            0.0,
        )

    try:
        parsed: dict[str, Any] = json.loads(response.content)
    except json.JSONDecodeError as exc:
        logger.warning("llm_choice_json_parse_failed", error=str(exc))
        return (
            None,
            "[LLM返回格式无效，使用默认选择]",
            0.5,
            "neutral",
            response.estimated_cost_usd,
        )

    chosen_idx = parsed.get("chosen_alt_index", 0)
    reasoning = parsed.get("reasoning", "")
    confidence = parsed.get("confidence", 0.5)

    # Clamp chosen_idx to valid range
    if not isinstance(chosen_idx, int) or not (0 <= chosen_idx < n_alternatives):
        chosen_idx = int(rng.integers(0, n_alternatives))
        reasoning = f"[LLM返回无效索引，随机选择] {reasoning}"

    # Clamp confidence
    if not isinstance(confidence, (int, float)):
        confidence = 0.5
    confidence = max(0.0, min(1.0, float(confidence)))

    return chosen_idx, reasoning, confidence, "neutral", response.estimated_cost_usd
