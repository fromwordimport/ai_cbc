"""CBC choice simulator — let virtual consumers answer choice sets.

Maps PersonaProfile traits to utility coefficients and selects alternatives
using a multinomial logit model.  Outputs CBCRawDataset and PersonaResponse.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from aicbc.core.models.persona import PersonaProfile
from aicbc.questionnaire.design.effects_coding import encode_profile, n_parameters
from aicbc.questionnaire.models import (
    Attribute,
    AttributeType,
    CBCQuestionnaire,
)
from aicbc.questionnaire.response_models import (
    AlternativeRecord,
    CBCRawDataset,
    ChoiceRecord,
    DatasetMetadata,
    PersonaResponse,
    SingleChoiceDetail,
)

# ---------------------------------------------------------------------------
# Trait → coefficient mapping helpers
# ---------------------------------------------------------------------------


def _price_coefficient_from_sensitivity(price_sensitivity: str) -> float:
    """Map price-sensitivity label to a negative price coefficient."""
    text = price_sensitivity.lower()
    if "极高" in text or "非常" in text or "极度" in text:
        return -2.0
    if "高" in text or "中高" in text:
        return -1.2
    if "中等" in text or "一般" in text:
        return -0.6
    if "低" in text or "不敏感" in text or "无所谓" in text:
        return -0.2
    return -0.8  # default moderate sensitivity


def _attribute_importance(
    attribute_id: str,
    decision_factors: list[str],
    ignored_factors: list[str],
) -> float:
    """Return an importance multiplier for an attribute.

    Checks whether any decision/ignored factor loosely matches the attribute id.
    """
    # If explicitly ignored, suppress
    for factor in ignored_factors:
        if _fuzzy_match(attribute_id, factor):
            return 0.1
    # If explicitly a decision factor, boost
    for factor in decision_factors:
        if _fuzzy_match(attribute_id, factor):
            return 1.5
    # Default moderate importance
    return 0.8


def _fuzzy_match(attribute_id: str, factor: str) -> bool:
    """Loose match between attribute id and a decision factor string."""
    attr = attribute_id.lower()
    fac = factor.lower()
    # Direct substring checks
    if attr in fac or fac in attr:
        return True
    # Known synonym mappings
    synonyms: dict[str, list[str]] = {
        "price": ["价格", "价钱", "售价", "成本", "预算", "价位"],
        "brand": ["品牌", "牌子", "口碑", "知名度", "信任度"],
        "capacity": ["容量", "大小", "套数", "规格", "尺寸", "空间"],
        "installation": ["安装", "嵌入", "台式", "水槽", "摆放", "布局"],
        "features": ["功能", "智能", "烘干", "除菌", "清洗", "模式"],
    }
    for key, words in synonyms.items():
        if attr == key:
            return any(w in fac for w in words)
        if fac == key or fac in words:
            return attr == key
    return False


# ---------------------------------------------------------------------------
# Utility coefficient builder
# ---------------------------------------------------------------------------


class PersonaUtilityMapper:
    """Build a utility coefficient vector β from a PersonaProfile."""

    def __init__(self, attributes: list[Attribute]) -> None:
        self.attributes = attributes
        self._param_offsets = self._build_offsets()

    def _build_offsets(self) -> dict[str, int]:
        """Map attribute id to its starting index in the β vector."""
        offsets: dict[str, int] = {}
        idx = 0
        for attr in self.attributes:
            offsets[attr.id] = idx
            if attr.type in (AttributeType.CATEGORICAL, AttributeType.ORDINAL):
                idx += len(attr.levels) - 1
            else:
                idx += 1
        return offsets

    def build_beta(self, persona: PersonaProfile) -> np.ndarray:
        """Return the utility coefficient vector β for *persona*."""
        n_params = n_parameters(self.attributes)
        beta = np.zeros(n_params, dtype=np.float64)

        l2 = persona.layer2_behavior
        ctx = persona.dishwasher_context

        for attr in self.attributes:
            offset = self._param_offsets[attr.id]

            if attr.type == AttributeType.PRICE:
                beta[offset] = _price_coefficient_from_sensitivity(
                    l2.price_sensitivity
                )
            elif attr.type in (AttributeType.CATEGORICAL, AttributeType.ORDINAL):
                n_levels = len(attr.levels)
                importance = _attribute_importance(
                    attr.id, ctx.decision_factors, ctx.ignored_factors
                )
                # Base coefficients: small random-ish variation per level
                base = np.random.default_rng(hash(persona.persona_id) % 2**31)
                level_coeffs = base.standard_normal(n_levels - 1) * 0.3
                level_coeffs += importance * 0.5  # shift mean by importance
                beta[offset : offset + n_levels - 1] = level_coeffs

                # Brand loyalty: boost the mentioned brand if applicable
                if attr.id == "brand":
                    _apply_brand_loyalty(beta, offset, attr, l2.brand_loyalty)
            elif attr.type == AttributeType.CONTINUOUS:
                importance = _attribute_importance(
                    attr.id, ctx.decision_factors, ctx.ignored_factors
                )
                beta[offset] = importance * 0.5

        return beta


def _apply_brand_loyalty(
    beta: np.ndarray,
    offset: int,
    attribute: Attribute,
    brand_loyalty: str,
) -> None:
    """Boost the coefficient of a favoured brand level."""
    loyalty_text = brand_loyalty.lower()
    for i, level in enumerate(attribute.levels[:-1]):  # last level is reference
        label = str(level.value).lower()
        if label in loyalty_text:
            beta[offset + i] += 1.0
            return
    # Also check if the last (reference) level is mentioned
    last_label = str(attribute.levels[-1].value).lower()
    if last_label in loyalty_text:
        # Boost all other levels negatively so reference is preferred
        for i in range(len(attribute.levels) - 1):
            beta[offset + i] -= 0.8


# ---------------------------------------------------------------------------
# Choice simulator
# ---------------------------------------------------------------------------


class CBCChoiceSimulator:
    """Simulate a persona's choices through a CBC questionnaire."""

    def __init__(self, attributes: list[Attribute]) -> None:
        self.attributes = attributes
        self.mapper = PersonaUtilityMapper(attributes)

    def simulate(
        self,
        persona: PersonaProfile,
        questionnaire: CBCQuestionnaire,
        *,
        deterministic: bool = False,
        include_none: bool = False,
        none_threshold: float = -1.5,
        seed: int | None = None,
    ) -> tuple[CBCRawDataset, PersonaResponse]:
        """Run the full questionnaire for a single persona.

        Args:
            persona: The virtual consumer.
            questionnaire: The CBC questionnaire to answer.
            deterministic: If True, always pick the max-utility option.
            include_none: If True, a "none" option with zero utility is added.
            none_threshold: Utility gap below which "none" becomes attractive.
            seed: Optional random seed for reproducibility.

        Returns:
            Tuple of (CBCRawDataset slice for this persona, PersonaResponse).
        """
        rng = np.random.default_rng(seed)
        beta = self.mapper.build_beta(persona)

        choice_records: list[ChoiceRecord] = []
        single_choices: list[SingleChoiceDetail] = []

        for cs_idx, cs in enumerate(questionnaire.choice_sets):
            alt_profiles = [alt.attributes for alt in cs.alternatives]

            # Encode all alternatives in the set
            utilities = np.array([
                float(encode_profile(p, self.attributes) @ beta)
                for p in alt_profiles
            ])

            # Handle "none" option
            if include_none:
                max_u = np.max(utilities)
                if max_u < none_threshold:
                    chosen_idx = None  # "none"
                else:
                    chosen_idx = int(np.argmax(utilities)) if deterministic else int(
                        rng.choice(len(utilities), p=_softmax(utilities))
                    )
            else:
                if deterministic:
                    chosen_idx = int(np.argmax(utilities))
                else:
                    chosen_idx = int(
                        rng.choice(len(utilities), p=_softmax(utilities))
                    )

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
                respondent_index=0,  # filled later by batch runner
                segment=persona.segment,
                choice_set_id=cs.choice_set_id,
                choice_set_index=cs_idx,
                alternatives=alt_records,
                none_chosen=(chosen_idx is None),
            ))

            single_choices.append(SingleChoiceDetail(
                choice_set_id=cs.choice_set_id,
                chosen_alt_index=chosen_idx,
                reasoning=_build_reasoning(chosen_idx, utilities, cs.alternatives),
                confidence=_compute_confidence(utilities, chosen_idx),
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

        persona_response = PersonaResponse(
            response_id=f"resp-{persona.persona_id}",
            study_id=questionnaire.study_id,
            persona_id=persona.persona_id,
            questionnaire_id=questionnaire.questionnaire_id,
            responses=single_choices,
            completion_status="COMPLETED",
            cost_cny=0.0,
        )

        return raw_dataset, persona_response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _softmax(utilities: np.ndarray) -> np.ndarray:
    """Stable softmax over utilities."""
    u = utilities - np.max(utilities)
    exp_u = np.exp(u)
    total = np.sum(exp_u)
    if total == 0:
        return np.ones_like(utilities) / len(utilities)
    return exp_u / total


def _compute_confidence(utilities: np.ndarray, chosen_idx: int | None) -> float:
    """Confidence = probability of chosen option under softmax."""
    if chosen_idx is None:
        return 0.5
    probs = _softmax(utilities)
    return float(probs[chosen_idx])


def _build_reasoning(
    chosen_idx: int | None,
    utilities: np.ndarray,
    alternatives: list[Any],
) -> str:
    """Generate a brief human-readable reasoning string."""
    if chosen_idx is None:
        return "所有选项都不满意，选择都不买"
    chosen = alternatives[chosen_idx]
    attrs = chosen.attributes
    # Pick the most distinctive attribute (price if present)
    if "price" in attrs:
        return f"价格¥{attrs['price']}符合预期，综合性价比最高"
    if "brand" in attrs:
        return f"偏好{attrs['brand']}品牌，满足核心需求"
    return "该选项在关键属性上最符合个人偏好"
