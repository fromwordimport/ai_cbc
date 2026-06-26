"""Models for product-context derivation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from aicbc.core.models.persona import DishwasherContext


class DerivedProductContext(BaseModel):
    """Dishwasher demand derived from a persona's life situation.

    This is produced by ProductContextDeriver (Task 2) and consumed by
    PlausibilityValidator (Task 1) and LanguageSampleGenerator (Task 5).
    """

    eligibility: Literal["not_applicable", "latent_need", "actively_considering"] = Field(
        ...,
        description="该产品情境对该画像是否适用",
    )
    reason: str = Field(
        ...,
        description="推导理由，用于反馈和诊断",
    )
    dishwasher_context: DishwasherContext = Field(
        ...,
        description="洗碗机购买情境",
    )
