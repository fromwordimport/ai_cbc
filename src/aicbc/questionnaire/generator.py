"""CBC questionnaire generator — orchestrates study creation and design generation."""

from __future__ import annotations

import structlog

from aicbc.questionnaire.design.d_optimal import generate_d_optimal_questionnaire
from aicbc.questionnaire.design.orthogonal import generate_balanced_questionnaire
from aicbc.questionnaire.models import (
    Attribute,
    AttributeLevel,
    AttributeType,
    CBCQuestionnaire,
    CBCStudy,
    DesignAlgorithm,
    DesignParameters,
    ProhibitedPair,
)

logger = structlog.get_logger("aicbc.questionnaire.generator")


def _dishwasher_default_attributes() -> list[Attribute]:
    """Return the default dishwasher CBC attributes."""
    return [
        Attribute(
            id="price",
            name="价格",
            type=AttributeType.PRICE,
            levels=[
                AttributeLevel(value="1999", label="1999元", description="入门级"),
                AttributeLevel(value="3999", label="3999元", description="主流性价比"),
                AttributeLevel(value="5999", label="5999元", description="中高端"),
                AttributeLevel(value="8999", label="8999元", description="高端旗舰"),
            ],
        ),
        Attribute(
            id="brand",
            name="品牌",
            type=AttributeType.CATEGORICAL,
            levels=[
                AttributeLevel(value="brand_1", label="华菱", description="极致性价比"),
                AttributeLevel(value="brand_2", label="美的", description="国民品牌"),
                AttributeLevel(value="brand_3", label="方太", description="本土高端"),
                AttributeLevel(value="brand_4", label="西门子", description="欧系高端"),
            ],
        ),
        Attribute(
            id="capacity",
            name="容量",
            type=AttributeType.CATEGORICAL,
            levels=[
                AttributeLevel(value="capacity_1", label="8套", description="2-3人家庭，紧凑型"),
                AttributeLevel(
                    value="capacity_2", label="14套", description="主流4-6人家庭，可洗锅"
                ),
                AttributeLevel(value="capacity_3", label="18套", description="多代同堂或餐具很多"),
                AttributeLevel(
                    value="capacity_4", label="24套", description="接近商用级，经常聚餐"
                ),
            ],
        ),
        Attribute(
            id="energy",
            name="能效等级",
            type=AttributeType.CATEGORICAL,
            levels=[
                AttributeLevel(value="energy_1", label="一级", description="最节能"),
                AttributeLevel(value="energy_2", label="二级", description="中等能耗"),
                AttributeLevel(value="energy_3", label="三级", description="偏低端"),
            ],
        ),
        Attribute(
            id="spray_arm",
            name="喷淋臂类型",
            type=AttributeType.CATEGORICAL,
            levels=[
                AttributeLevel(
                    value="spray_arm_1", label="上下双层", description="基础配置，仅中层+底层"
                ),
                AttributeLevel(
                    value="spray_arm_2", label="三层", description="增加顶部喷淋，覆盖面更全"
                ),
                AttributeLevel(
                    value="spray_arm_3", label="多向旋喷", description="360°旋转喷淋，死角无残留"
                ),
            ],
        ),
        Attribute(
            id="installation",
            name="安装方式",
            type=AttributeType.CATEGORICAL,
            levels=[
                AttributeLevel(
                    value="installation_1", label="嵌入式", description="需定制橱柜，美观统一"
                ),
                AttributeLevel(
                    value="installation_2", label="独立式", description="摆放灵活，免改装"
                ),
                AttributeLevel(
                    value="installation_3",
                    label="台式",
                    description="小体积，免安装，适合出租或小厨房",
                ),
                AttributeLevel(
                    value="installation_4", label="水槽式", description="不占橱柜空间，替换原水槽"
                ),
            ],
        ),
        Attribute(
            id="drying",
            name="烘干方式",
            type=AttributeType.CATEGORICAL,
            levels=[
                AttributeLevel(value="drying_1", label="余热", description="依靠高温余温蒸发水分"),
                AttributeLevel(value="drying_2", label="热交换", description="通过冷水壁冷凝"),
                AttributeLevel(
                    value="drying_3", label="热风", description="主动热风循环，餐具干爽"
                ),
                AttributeLevel(value="drying_4", label="晶蕾", description="吸湿放热，省电且全干"),
            ],
        ),
    ]


class QuestionnaireGenerator:
    """Orchestrates CBC study creation and questionnaire generation."""

    def create_study(
        self,
        study_id: str,
        product_category: str,
        research_goal: str,
        attributes: list[Attribute] | None = None,
        design_parameters: DesignParameters | None = None,
        target_segments: list[str] | None = None,
        prohibited_pairs: list[ProhibitedPair] | None = None,
    ) -> CBCStudy:
        """Create a new CBC study definition.

        If *attributes* is None, defaults to the dishwasher attribute set.
        """
        if attributes is None:
            attributes = _dishwasher_default_attributes()

        study = CBCStudy(
            study_id=study_id,
            product_category=product_category,
            research_goal=research_goal,
            attributes=attributes,
            design_parameters=design_parameters or DesignParameters(),
            target_segments=target_segments or [],
            prohibited_pairs=prohibited_pairs or [],
        )
        logger.info("study_created", study_id=study_id, n_attributes=len(attributes))
        return study

    def generate_questionnaire(
        self,
        study: CBCStudy,
        seed: int | None = None,
    ) -> CBCQuestionnaire:
        """Generate a questionnaire for the given study.

        Routes to the algorithm specified in study.design_parameters.
        """
        log = logger.bind(study_id=study.study_id)
        log.info(
            "questionnaire_generation_start",
            algorithm=study.design_parameters.algorithm.value,
        )

        # Use explicit seed if provided, otherwise fall back to study's seed.
        # Must use `is not None` — seed=0 is a valid value but falsy.
        effective_seed = seed if seed is not None else study.design_parameters.seed

        if study.design_parameters.algorithm == DesignAlgorithm.BALANCED:
            questionnaire = generate_balanced_questionnaire(
                study_id=study.study_id,
                attributes=study.attributes,
                design_parameters=study.design_parameters,
                seed=effective_seed,
            )
        else:
            questionnaire = generate_d_optimal_questionnaire(
                study_id=study.study_id,
                attributes=study.attributes,
                design_parameters=study.design_parameters,
                prohibited_pairs=study.prohibited_pairs,
                seed=effective_seed,
            )

        log.info(
            "questionnaire_generation_complete",
            d_efficiency=questionnaire.d_efficiency,
            a_efficiency=questionnaire.a_efficiency,
            iterations=questionnaire.iterations,
        )
        return questionnaire
