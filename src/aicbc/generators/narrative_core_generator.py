"""NarrativeCoreGenerator — produces MiniBiography and SceneReactions from four layers."""

from __future__ import annotations

import json
from pathlib import Path

import structlog

from aicbc.core.models.persona import (
    MiniBiography,
    PersonaProfile,
    SceneReactions,
)
from aicbc.llm.client import LLMClient

logger = structlog.get_logger("aicbc.generators")

DEFAULT_PROMPT_PATH = (
    Path(__file__).parents[3] / "configs" / "prompts" / "narrative_core_generation.txt"
)

_DEFAULT_MINI_BIO = MiniBiography(
    past="成长过程中的一次具体消费经历塑造了她的价值观。",
    present="在日常工作和家庭责任之间寻找平衡。",
    future="担忧即将到来的大额支出与生活质量之间的冲突。",
)

_DEFAULT_SCENES = SceneReactions(
    under_pressure="压力下会先搜索信息但延迟决策",
    friend_recommendation="会询问细节但保持独立判断",
    flash_sale_limited="容易冲动加购但可能不结算",
    found_cheaper_elsewhere="感到后悔并考虑退换",
    product_fault_after_sales="先查攻略再联系售后",
)


class NarrativeCoreGenerator:
    """Generate the narrative core (mini-biography + scene reactions) for a persona."""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        prompt_template_path: Path | str | None = None,
    ) -> None:
        self._llm = llm_client or LLMClient()
        self._prompt_path = (
            Path(prompt_template_path) if prompt_template_path else DEFAULT_PROMPT_PATH
        )
        self._template = self._prompt_path.read_text(encoding="utf-8")

    def generate(self, persona: PersonaProfile) -> tuple[MiniBiography, SceneReactions]:
        """Generate MiniBiography and SceneReactions from the four-layer persona."""
        prompt = self._build_prompt(persona)
        try:
            response = self._llm.generate(
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个资深的消费者研究专家，擅长把标签化画像还原成有故事的人。",
                    },
                    {"role": "user", "content": prompt},
                ],
                json_mode=True,
            )
            parsed = json.loads(response.content)
        except Exception as exc:
            logger.warning(
                "narrative_core_generation_failed",
                error=str(exc),
                persona_id=persona.persona_id,
            )
            return _DEFAULT_MINI_BIO, _DEFAULT_SCENES

        mini_bio_data = parsed.get("mini_biography", {})
        mini_bio = MiniBiography(
            past=mini_bio_data.get("past", _DEFAULT_MINI_BIO.past),
            present=mini_bio_data.get("present", _DEFAULT_MINI_BIO.present),
            future=mini_bio_data.get("future", _DEFAULT_MINI_BIO.future),
        )

        scenes_data = parsed.get("scene_reactions", {})
        scenes = SceneReactions(
            under_pressure=scenes_data.get("under_pressure", _DEFAULT_SCENES.under_pressure),
            friend_recommendation=scenes_data.get(
                "friend_recommendation", _DEFAULT_SCENES.friend_recommendation
            ),
            flash_sale_limited=scenes_data.get(
                "flash_sale_limited", _DEFAULT_SCENES.flash_sale_limited
            ),
            found_cheaper_elsewhere=scenes_data.get(
                "found_cheaper_elsewhere", _DEFAULT_SCENES.found_cheaper_elsewhere
            ),
            product_fault_after_sales=scenes_data.get(
                "product_fault_after_sales", _DEFAULT_SCENES.product_fault_after_sales
            ),
        )

        return mini_bio, scenes

    def _build_prompt(self, persona: PersonaProfile) -> str:
        l1 = persona.layer1_demographics
        l2 = persona.layer2_behavior
        l3 = persona.layer3_psychology
        l4 = persona.layer4_scenarios
        tension = l3.tension_combination

        return self._template.format(
            layer1_summary=(
                f"{l1.age}, {l1.gender}, {l1.city}, {l1.income}, {l1.occupation}, "
                f"{l1.education}, {l1.marital_status}, {l1.living_type}"
            ),
            decision_style=l2.decision_style,
            price_sensitivity=l2.price_sensitivity,
            core_values=", ".join(l3.core_values),
            core_anxieties=", ".join(l3.core_anxieties),
            tension_labels=", ".join(tension.labels),
            tension_narrative=tension.narrative_explanation,
            secret_motivation=l3.secret_motivation,
            defense_mechanism=l3.defense_mechanism,
            daily_routine=l4.daily_routine,
            purchase_trigger=l4.purchase_trigger,
            stress_response=l4.stress_response,
        )
