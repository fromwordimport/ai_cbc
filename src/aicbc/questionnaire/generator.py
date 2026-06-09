"""CBC questionnaire generator — orchestrates study creation and design generation."""

from __future__ import annotations

import structlog

from aicbc.questionnaire.design.d_optimal import generate_d_optimal_questionnaire
from aicbc.questionnaire.design.orthogonal import generate_orthogonal_questionnaire
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
    """Return the default dishwasher CBC attributes from the design spec."""
    return [
        Attribute(
            id="price",
            name="价格",
            type=AttributeType.PRICE,
            levels=[
                AttributeLevel(value=2999, label="¥2,999", description="入门级"),
                AttributeLevel(value=3999, label="¥3,999", description="主流价位"),
                AttributeLevel(value=4999, label="¥4,999", description="中高端"),
                AttributeLevel(value=5999, label="¥5,999", description="旗舰级"),
            ],
        ),
        Attribute(
            id="capacity",
            name="容量",
            type=AttributeType.CATEGORICAL,
            levels=[
                AttributeLevel(value="6套", label="6套（1-2人）", description="单身/情侣"),
                AttributeLevel(value="10套", label="10套（3-4人）", description="小家庭"),
                AttributeLevel(value="13套", label="13套（5人以上）", description="大家庭"),
            ],
        ),
        Attribute(
            id="installation",
            name="安装方式",
            type=AttributeType.CATEGORICAL,
            levels=[
                AttributeLevel(value="台式", label="台式（免安装）", description="灵活、租房友好"),
                AttributeLevel(value="嵌入式", label="嵌入式", description="省空间、美观"),
                AttributeLevel(value="水槽式", label="水槽式", description="替换水槽、不占地"),
            ],
        ),
        Attribute(
            id="features",
            name="核心功能",
            type=AttributeType.CATEGORICAL,
            levels=[
                AttributeLevel(value="基础", label="标准洗+热风烘干", description="满足基本洗碗需求"),
                AttributeLevel(value="智能", label="智能洗+烘干+72℃高温除菌", description="智能识别脏污程度"),
                AttributeLevel(value="全能", label="AI智能洗+烘干+UV除菌+智能投放", description="全自动、最省心"),
            ],
        ),
        Attribute(
            id="brand",
            name="品牌",
            type=AttributeType.CATEGORICAL,
            levels=[
                AttributeLevel(value="美的", label="美的", description="国民品牌、性价比"),
                AttributeLevel(value="西门子", label="西门子", description="德系精工、高端"),
                AttributeLevel(value="方太", label="方太", description="厨电专家、本土化"),
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

        if study.design_parameters.algorithm == DesignAlgorithm.ORTHOGONAL:
            questionnaire = generate_orthogonal_questionnaire(
                study_id=study.study_id,
                attributes=study.attributes,
                design_parameters=study.design_parameters,
                seed=seed or study.design_parameters.seed,
            )
        else:
            questionnaire = generate_d_optimal_questionnaire(
                study_id=study.study_id,
                attributes=study.attributes,
                design_parameters=study.design_parameters,
                prohibited_pairs=study.prohibited_pairs,
                seed=seed or study.design_parameters.seed,
            )

        log.info(
            "questionnaire_generation_complete",
            d_efficiency=questionnaire.d_efficiency,
            a_efficiency=questionnaire.a_efficiency,
            iterations=questionnaire.iterations,
        )
        return questionnaire
