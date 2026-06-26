"""ProductContextDeriver — derive dishwasher context from persona reality."""

from __future__ import annotations

import json
from pathlib import Path

import structlog

from aicbc.core.models.persona import DishwasherContext, PersonaProfile
from aicbc.core.validators.product_context_models import DerivedProductContext
from aicbc.llm.client import LLMClient

logger = structlog.get_logger("aicbc.validators")

DEFAULT_PROMPT_PATH = (
    Path(__file__).parents[4] / "configs" / "prompts" / "product_context_derivation.txt"
)


def _has_independent_kitchen(living_type: str) -> bool:
    """Return False for living situations that physically cannot host a dishwasher."""
    impossible = {"宿舍", "合租房", "无厨房"}
    return not any(marker in living_type for marker in impossible)


def evaluate_hard_constraints(persona: PersonaProfile) -> DerivedProductContext | None:
    """Evaluate hard physical constraints; return DerivedProductContext if ineligible, else None.

    This shared function is used by both ProductContextDeriver and ProfileGenerator
    to ensure consistent hard-constraint evaluation without code duplication.
    """
    l1 = persona.layer1_demographics

    if "学生" in l1.life_stage and "宿舍" in l1.living_type:
        return DerivedProductContext(
            eligibility="not_applicable",
            reason="学生住宿舍通常无独立厨房和水电安装条件",
            dishwasher_context=DishwasherContext(
                purchase_constraints=["无独立厨房，无法安装"],
                decision_factors=[],
                ignored_factors=[],
            ),
        )

    if not _has_independent_kitchen(l1.living_type):
        return DerivedProductContext(
            eligibility="not_applicable",
            reason=f"居住形态 '{l1.living_type}' 不具备独立厨房",
            dishwasher_context=DishwasherContext(
                purchase_constraints=["无独立厨房，无法安装"],
                decision_factors=[],
                ignored_factors=[],
            ),
        )

    return None


class ProductContextDeriver:
    """Derive whether and how a persona would consider a dishwasher."""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        prompt_template_path: Path | str | None = None,
    ) -> None:
        self._llm = llm_client or LLMClient()
        self._prompt_path = Path(prompt_template_path) if prompt_template_path else DEFAULT_PROMPT_PATH
        self._template = self._prompt_path.read_text(encoding="utf-8")

    def derive(self, persona: PersonaProfile) -> DerivedProductContext:
        """Return derived product context based on persona reality."""
        # Hard physical constraints first — no LLM needed.
        hard_result = evaluate_hard_constraints(persona)
        if hard_result is not None:
            return hard_result

        # Fall back to LLM for nuanced cases.
        prompt = self._build_prompt(persona)
        try:
            response = self._llm.generate(
                messages=[
                    {"role": "system", "content": "你是一个严谨的消费者研究分析师。"},
                    {"role": "user", "content": prompt},
                ],
                json_mode=True,
            )
            parsed = json.loads(response.content)
        except Exception as exc:
            logger.warning(
                "product_context_derivation_failed",
                error=str(exc),
                persona_id=persona.persona_id,
            )
            return DerivedProductContext(
                eligibility="not_applicable",
                reason="推导失败，默认认为当前不考虑洗碗机",
                dishwasher_context=DishwasherContext(),
            )

        return DerivedProductContext(
            eligibility=parsed.get("eligibility", "not_applicable"),
            reason=parsed.get("reason", ""),
            dishwasher_context=DishwasherContext(
                purchase_constraints=parsed.get("dishwasher_context", {}).get(
                    "purchase_constraints", []
                ),
                decision_factors=parsed.get("dishwasher_context", {}).get(
                    "decision_factors", []
                ),
                ignored_factors=parsed.get("dishwasher_context", {}).get(
                    "ignored_factors", []
                ),
            ),
        )

    def _build_prompt(self, persona: PersonaProfile) -> str:
        l1 = persona.layer1_demographics
        l2 = persona.layer2_behavior
        l4 = persona.layer4_scenarios
        return self._template.format(
            life_stage=l1.life_stage,
            living_type=l1.living_type,
            income=l1.income,
            marital_status=l1.marital_status,
            price_sensitivity=l2.price_sensitivity,
            decision_style=l2.decision_style,
            daily_routine=l4.daily_routine,
            purchase_trigger=l4.purchase_trigger,
        )
