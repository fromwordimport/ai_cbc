"""Data pipeline tools — PersonaProfile → CBCRawDataset → AnalysisResult.

Implements the three core data-flow tools that bridge the AI_CBC
subsystems, using the ToolCalling protocol.
"""

from __future__ import annotations

from typing import Any

import structlog

from aicbc.analysis.models import AnalysisResultResponse
from aicbc.core.models.persona import PersonaProfile
from aicbc.questionnaire.models import Attribute, CBCQuestionnaire
from aicbc.questionnaire.response_models import CBCRawDataset
from aicbc.tools.protocol import (
    ToolParameter,
    ToolSpec,
    register_tool,
)

logger = structlog.get_logger("aicbc.tools.pipeline")


# ---------------------------------------------------------------------------
# Tool 1: persona_to_questionnaire_context
# ---------------------------------------------------------------------------


def persona_to_questionnaire_context(
    persona: dict[str, Any],
    questionnaire: dict[str, Any],
) -> dict[str, Any]:
    """Bind a PersonaProfile to a CBCQuestionnaire, producing simulation context.

    This is the bridge from *consumer simulation* to *questionnaire*.
    It extracts persona-relevant attributes and injects them into the
    questionnaire context so the simulation agent can make choices
    consistent with the persona's profile.

    Args:
        persona: Serialized ``PersonaProfile`` dict.
        questionnaire: Serialized ``CBCQuestionnaire`` dict.

    Returns:
        A context dict containing:
        - ``persona_summary``: condensed persona description
        - ``relevant_attributes``: persona-relevant attribute weights
        - ``scenario_injection``: situational narrative for the choice task
    """
    log = logger.bind(persona_id=persona.get("persona_id"), study_id=questionnaire.get("study_id"))
    log.info("binding_persona_to_questionnaire")

    layer1 = persona.get("layer1_demographics", {})
    layer2 = persona.get("layer2_behavior", {})
    layer3 = persona.get("layer3_psychology", {})
    layer4 = persona.get("layer4_scenarios", {})
    dw_ctx = persona.get("dishwasher_context", {})

    # Build a concise persona narrative for the LLM prompt
    summary_parts = [
        f"消费者画像：{layer1.get('age', '')}，{layer1.get('gender', '')}，",
        f"居住于{layer1.get('city', '')}，{layer1.get('occupation', '')}，",
        f"月收入{layer1.get('income', '')}。",
        f"决策风格：{layer2.get('decision_style', '')}。",
        f"价格敏感度：{layer2.get('price_sensitivity', '')}。",
    ]

    # Extract tension narrative for injection
    tension = layer3.get("tension_combination", {})
    tension_narrative = tension.get("narrative_explanation", "")

    # Build scenario injection from Layer 4
    scenario_parts = [
        layer4.get("daily_routine", ""),
        layer4.get("purchase_trigger", ""),
        layer4.get("stress_response", ""),
    ]

    # Relevant attributes: map persona traits to product attributes
    relevant_attrs: dict[str, float] = {}
    decision_factors = dw_ctx.get("decision_factors", [])
    ignored_factors = dw_ctx.get("ignored_factors", [])

    # Weight attributes based on persona's stated decision factors
    for factor in decision_factors:
        relevant_attrs[factor] = 1.5  # High weight
    for factor in ignored_factors:
        relevant_attrs[factor] = 0.3  # Low weight

    result = {
        "persona_summary": "".join(summary_parts),
        "tension_narrative": tension_narrative,
        "scenario_injection": " ".join(filter(None, scenario_parts)),
        "relevant_attributes": relevant_attrs,
        "purchase_constraints": dw_ctx.get("purchase_constraints", []),
        "language_samples": persona.get("language_samples", []),
        "authenticity_score": persona.get("authenticity_score"),
    }

    log.info("persona_questionnaire_context_built", factor_count=len(decision_factors))
    return result


register_tool(
    persona_to_questionnaire_context,
    spec=ToolSpec(
        name="persona_to_questionnaire_context",
        description="将消费者画像绑定到CBC问卷，生成模拟上下文",
        parameters=[
            ToolParameter(
                name="persona",
                type="object",
                description="序列化的PersonaProfile字典",
                required=True,
            ),
            ToolParameter(
                name="questionnaire",
                type="object",
                description="序列化的CBCQuestionnaire字典",
                required=True,
            ),
        ],
        returns={"type": "object", "description": "模拟上下文字典"},
        timeout_seconds=5.0,
        max_retries=0,
    ),
)


# ---------------------------------------------------------------------------
# Tool 2: responses_to_raw_dataset
# ---------------------------------------------------------------------------


def responses_to_raw_dataset(
    responses: list[dict[str, Any]],
    study_id: str,
    attributes: list[dict[str, Any]],
    questionnaire: dict[str, Any],
) -> dict[str, Any]:
    """Aggregate PersonaResponse list into a CBCRawDataset.

    This is the bridge from *questionnaire / simulation* to *analysis*.
    It transforms individual persona responses into the standardized
    ``CBCRawDataset`` format required by the analysis engine.

    Args:
        responses: List of serialized ``PersonaResponse`` dicts.
        study_id: Study identifier.
        attributes: List of serialized ``Attribute`` dicts.
        questionnaire: Serialized ``CBCQuestionnaire`` dict.

    Returns:
        Serialized ``CBCRawDataset`` dict.
    """
    log = logger.bind(study_id=study_id, n_responses=len(responses))
    log.info("aggregating_responses_to_dataset")

    if not responses:
        raise ValueError("responses list cannot be empty")

    # Extract metadata from questionnaire
    choice_sets = questionnaire.get("choice_sets", [])
    design_params = questionnaire.get("design_parameters", {})
    n_alternatives = design_params.get("n_alternatives", 3)

    # Build choice records
    choice_records: list[dict[str, Any]] = []
    for resp_idx, resp in enumerate(responses):
        persona_id = resp.get("persona_id", f"resp-{resp_idx}")
        segment = resp.get("segment", "unknown")
        resp_choices = resp.get("responses", [])

        for cs in choice_sets:
            cs_id = cs.get("choice_set_id", 1)
            alternatives = cs.get("alternatives", [])

            # Build alternative records with chosen flag
            alt_records: list[dict[str, Any]] = []
            chosen_idx = None

            # Find which alternative was chosen from the response
            for rc in resp_choices:
                if rc.get("choice_set_id") == cs_id:
                    chosen_idx = rc.get("chosen_alt_index")
                    break

            for alt in alternatives:
                alt_idx = alt.get("alt_index", 0)
                alt_records.append({
                    "alt_index": alt_idx,
                    "chosen": alt_idx == chosen_idx if chosen_idx is not None else False,
                    "attributes": alt.get("attributes", {}),
                })

            # Determine none_chosen
            none_chosen = chosen_idx is None

            choice_records.append({
                "respondent_id": persona_id,
                "respondent_index": resp_idx,
                "segment": segment,
                "choice_set_id": cs_id,
                "choice_set_index": cs_id - 1,
                "alternatives": alt_records,
                "none_chosen": none_chosen,
            })

    dataset = {
        "metadata": {
            "study_id": study_id,
            "n_respondents": len(responses),
            "n_choice_sets": len(choice_sets),
            "n_alternatives": n_alternatives,
            "attributes": attributes,
        },
        "choice_records": choice_records,
    }

    log.info(
        "dataset_aggregated",
        n_records=len(choice_records),
        n_respondents=len(responses),
    )
    return dataset


register_tool(
    responses_to_raw_dataset,
    spec=ToolSpec(
        name="responses_to_raw_dataset",
        description="将消费者作答列表聚合为标准交换数据集CBCRawDataset",
        parameters=[
            ToolParameter(
                name="responses",
                type="array",
                description="PersonaResponse序列化字典列表",
                required=True,
            ),
            ToolParameter(
                name="study_id",
                type="string",
                description="研究标识",
                required=True,
            ),
            ToolParameter(
                name="attributes",
                type="array",
                description="属性定义列表",
                required=True,
            ),
            ToolParameter(
                name="questionnaire",
                type="object",
                description="问卷字典",
                required=True,
            ),
        ],
        returns={"type": "object", "description": "CBCRawDataset序列化字典"},
        timeout_seconds=10.0,
        max_retries=1,
    ),
)


# ---------------------------------------------------------------------------
# Tool 3: analysis_result_to_report_context
# ---------------------------------------------------------------------------


def analysis_result_to_report_context(
    analysis_result: dict[str, Any],
    attributes: list[dict[str, Any]],
    study_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Transform AnalysisResult into report-generation context.

    This is the bridge from *analysis* to *reporting / dashboard*.
    It structures the analysis output into a format suitable for
    natural-language report generation and dashboard rendering.

    Args:
        analysis_result: Serialized ``AnalysisResultResponse`` dict.
        attributes: List of serialized ``Attribute`` dicts.
        study_metadata: Optional study-level metadata.

    Returns:
        A context dict for report generation containing:
        - ``summary``: executive summary
        - ``key_findings``: ranked list of insights
        - ``charts_data``: structured data for visualization
        - ``recommendations``: actionable recommendations
    """
    log = logger.bind(
        analysis_id=analysis_result.get("analysis_id"),
        study_id=analysis_result.get("study_id"),
    )
    log.info("transforming_analysis_to_report_context")

    # Extract core data
    importance = analysis_result.get("importance", {})
    population_params = analysis_result.get("population_params", {})
    convergence = analysis_result.get("convergence", {})
    wtp = analysis_result.get("wtp", {})
    model_type = analysis_result.get("model_type", "unknown")

    # Sort importance for ranking
    sorted_importance = sorted(
        importance.items(),
        key=lambda x: x[1],
        reverse=True,
    )

    # Build attribute name mapping
    attr_name_map = {a.get("id", ""): a.get("name", "") for a in attributes}

    # Key findings
    findings: list[str] = []
    if sorted_importance:
        top_attr, top_val = sorted_importance[0]
        findings.append(
            f"最重要的属性是'{attr_name_map.get(top_attr, top_attr)}'"
            f"（重要性={top_val:.1%}）"
        )
    if len(sorted_importance) > 1:
        second_attr, second_val = sorted_importance[1]
        findings.append(
            f"其次为'{attr_name_map.get(second_attr, second_attr)}'"
            f"（重要性={second_val:.1%}）"
        )

    # Convergence assessment
    converged = convergence.get("converged", False)
    rhat_max = convergence.get("rhat_max", 0.0)
    if converged:
        conv_text = f"模型收敛良好 (R-hat max={rhat_max:.3f})"
    else:
        conv_text = f"模型未完全收敛 (R-hat max={rhat_max:.3f})，建议增加采样"
    findings.append(conv_text)

    # WTP summary
    wtp_findings: list[str] = []
    if wtp and isinstance(wtp, dict):
        wtp_values = wtp.get("wtp_values", {})
        for attr_id, attr_wtp in wtp_values.items():
            comparisons = attr_wtp.get("comparisons", []) if isinstance(attr_wtp, dict) else []
            if comparisons:
                wtp_findings.append(
                    f"{attr_name_map.get(attr_id, attr_id)}: "
                    f"包含{len(comparisons)}个水平对比"
                )

    # Charts data
    charts_data = {
        "importance": {
            "labels": [attr_name_map.get(a, a) for a, _ in sorted_importance],
            "values": [v for _, v in sorted_importance],
        },
        "convergence": {
            "rhat_max": rhat_max,
            "ess_min": convergence.get("ess_bulk_min", 0),
            "converged": converged,
        },
        "wtp": wtp_findings,
    }

    # Recommendations
    recommendations: list[str] = []
    if not converged:
        recommendations.append("增加MCMC采样次数（n_draws ≥ 2000, n_tune ≥ 2000）")
    if sorted_importance:
        top_attr_id = sorted_importance[0][0]
        recommendations.append(
            f"优先优化'{attr_name_map.get(top_attr_id, top_attr_id)}'属性，"
            f"其对消费者决策影响最大"
        )

    result = {
        "summary": (
            f"联合分析完成（{model_type.upper()}模型）。"
            f"共{len(analysis_result.get('individual_utilities', {}))}位受访者的个体效用已估计。"
            f"{conv_text}"
        ),
        "key_findings": findings,
        "charts_data": charts_data,
        "recommendations": recommendations,
        "model_type": model_type,
        "processing_time": analysis_result.get("processing_time_seconds", 0),
        "study_metadata": study_metadata or {},
    }

    log.info("report_context_built", findings_count=len(findings))
    return result


register_tool(
    analysis_result_to_report_context,
    spec=ToolSpec(
        name="analysis_result_to_report_context",
        description="将分析结果转换为报告生成上下文",
        parameters=[
            ToolParameter(
                name="analysis_result",
                type="object",
                description="序列化的AnalysisResultResponse字典",
                required=True,
            ),
            ToolParameter(
                name="attributes",
                type="array",
                description="属性定义列表",
                required=True,
            ),
            ToolParameter(
                name="study_metadata",
                type="object",
                description="研究元数据（可选）",
                required=False,
                default=None,
            ),
        ],
        returns={"type": "object", "description": "报告生成上下文字典"},
        timeout_seconds=5.0,
        max_retries=0,
    ),
)


# ---------------------------------------------------------------------------
# Tool 4: validate_data_flow
# ---------------------------------------------------------------------------


def validate_data_flow(
    source_type: str,
    target_type: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Validate that data conforms to the expected flow contract.

    Checks structural compatibility between subsystem data formats.

    Args:
        source_type: Source format name (e.g. "PersonaProfile").
        target_type: Target format name (e.g. "CBCRawDataset").
        data: The data to validate.

    Returns:
        Validation result with ``valid`` flag and ``errors`` list.
    """
    log = logger.bind(source=source_type, target=target_type)
    log.info("validating_data_flow")

    errors: list[str] = []

    # PersonaProfile → CBCRawDataset validation
    if source_type == "PersonaProfile" and target_type == "CBCRawDataset":
        required_persona_fields = [
            "persona_id", "segment", "layer1_demographics",
            "layer2_behavior", "layer3_psychology", "layer4_scenarios",
        ]
        for field in required_persona_fields:
            if field not in data:
                errors.append(f"Missing required PersonaProfile field: {field}")

    # CBCRawDataset → AnalysisResult validation
    elif source_type == "CBCRawDataset" and target_type == "AnalysisResult":
        if "metadata" not in data:
            errors.append("Missing CBCRawDataset.metadata")
        else:
            meta = data["metadata"]
            for field in ["study_id", "n_respondents", "n_choice_sets", "n_alternatives"]:
                if field not in meta:
                    errors.append(f"Missing metadata field: {field}")

        if "choice_records" not in data or not data["choice_records"]:
            errors.append("CBCRawDataset.choice_records is empty")

    # Unknown flow
    else:
        errors.append(f"Unknown data flow: {source_type} → {target_type}")

    valid = len(errors) == 0
    log.info("data_flow_validation_complete", valid=valid, error_count=len(errors))

    return {"valid": valid, "errors": errors, "source": source_type, "target": target_type}


register_tool(
    validate_data_flow,
    spec=ToolSpec(
        name="validate_data_flow",
        description="验证子系统间数据流的结构兼容性",
        parameters=[
            ToolParameter(
                name="source_type",
                type="string",
                description="源数据格式名称",
                required=True,
            ),
            ToolParameter(
                name="target_type",
                type="string",
                description="目标数据格式名称",
                required=True,
            ),
            ToolParameter(
                name="data",
                type="object",
                description="待验证的数据",
                required=True,
            ),
        ],
        returns={"type": "object", "description": "验证结果"},
        timeout_seconds=3.0,
        max_retries=0,
    ),
)
