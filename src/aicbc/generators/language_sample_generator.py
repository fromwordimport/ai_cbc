"""LanguageSampleGenerator — generates voice-consistent language samples."""

from __future__ import annotations

import json
from pathlib import Path

import structlog

from aicbc.core.models.persona import PersonaProfile
from aicbc.llm.client import LLMClient

logger = structlog.get_logger("aicbc.generators")

DEFAULT_PROMPT_PATH = (
    Path(__file__).parents[3] / "configs" / "prompts" / "language_sample_generation.txt"
)

_DEFAULT_SAMPLES = [
    "洗碗机真的好用吗？我看网上评价褒贬不一，有点纠结。",
    "价格倒是其次，主要是怕买了之后家里老人不会用，放着积灰。",
    "如果真能省出每天洗碗的时间，我觉得多花点钱也值得考虑。",
]


class LanguageSampleGenerator:
    """Generate 3 language samples that sound like the persona."""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        prompt_template_path: Path | str | None = None,
    ) -> None:
        self._llm = llm_client or LLMClient()
        self._prompt_path = Path(prompt_template_path) if prompt_template_path else DEFAULT_PROMPT_PATH
        self._template = self._prompt_path.read_text(encoding="utf-8")

    def generate(self, persona: PersonaProfile) -> list[str]:
        """Generate 3 language samples from the persona's narrative core."""
        prompt = self._build_prompt(persona)
        try:
            response = self._llm.generate(
                messages=[
                    {"role": "system", "content": "你是一个消费者研究专家，擅长模仿真实人物的说话方式。"},
                    {"role": "user", "content": prompt},
                ],
                json_mode=True,
            )
            parsed = json.loads(response.content)
        except Exception as exc:
            logger.warning(
                "language_sample_generation_failed",
                error=str(exc),
                persona_id=persona.persona_id,
            )
            return list(_DEFAULT_SAMPLES)

        samples = parsed.get("language_samples", [])
        if not isinstance(samples, list) or len(samples) != 3:
            logger.warning(
                "language_sample_count_invalid",
                count=len(samples) if isinstance(samples, list) else None,
            )
            return list(_DEFAULT_SAMPLES)

        validated: list[str] = []
        for sample in samples:
            if isinstance(sample, str) and 20 <= len(sample.strip()) <= 60:
                validated.append(sample.strip())
            else:
                validated.append(_DEFAULT_SAMPLES[len(validated)])

        return validated

    def _build_prompt(self, persona: PersonaProfile) -> str:
        bio = persona.mini_biography
        scenes = persona.scene_reactions
        l2 = persona.layer2_behavior
        l3 = persona.layer3_psychology

        bio_text = ""
        if bio:
            bio_text = f"过去：{bio.past}\n现在：{bio.present}\n未来：{bio.future}"

        scene_text = ""
        if scenes:
            scene_text = (
                f"压力大时：{scenes.under_pressure}\n"
                f"朋友推荐时：{scenes.friend_recommendation}\n"
                f"大促限时：{scenes.flash_sale_limited}\n"
                f"发现更低价时：{scenes.found_cheaper_elsewhere}\n"
                f"售后故障时：{scenes.product_fault_after_sales}"
            )

        return self._template.format(
            decision_style=l2.decision_style,
            defense_mechanism=l3.defense_mechanism,
            bio_text=bio_text,
            scene_text=scene_text,
        )
