"""Subsystem tools — standardized tool wrappers for AI_CBC subsystems.

Wraps the three core subsystems as ToolCalling-compatible tools:
  1. Consumer Simulation (画像生成 + 选择模拟)
  2. CBC Questionnaire (实验设计 + 问卷生成)
  3. Data Analysis (HB/MNL模型 + 结果计算)

Each tool follows the ToolCalling protocol (ToolSpec, validation, timeout,
structured result) and operates on the standard data entities defined in
``docs/数据字典.md``.
"""

from __future__ import annotations

from typing import Any

import structlog

from aicbc.agents.analysis_agent import AnalysisAgent, AnalysisAgentConfig
from aicbc.agents.consumer_generator import ConsumerGeneratorAgent
from aicbc.core.models.persona import PersonaProfile
from aicbc.core.simulation.cbc_choice_simulator import CBCChoiceSimulator
from aicbc.questionnaire.generator import QuestionnaireGenerator
from aicbc.questionnaire.models import Attribute, CBCStudy, DesignParameters
from aicbc.questionnaire.response_models import CBCRawDataset
from aicbc.tools.protocol import (
    ToolParameter,
    ToolSpec,
    register_tool,
)

logger = structlog.get_logger("aicbc.tools.subsystems")


# ---------------------------------------------------------------------------
# Tool 1: generate_persona
# ---------------------------------------------------------------------------


def generate_persona(
    study_id: str,
    index: int,
    life_stage: str | None = None,
    anxieties: list[str] | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    """Generate a single virtual consumer persona.

    Wraps ``ConsumerGeneratorAgent`` as a ToolCalling-compatible function.
    Produces a four-layer PersonaProfile with authenticity scoring.

    Args:
        study_id: Parent study identifier.
        index: Persona index for ID generation (e.g. 0 → persona-{study_id}-0000).
        life_stage: Optional life stage override (e.g. "精致白领").
        anxieties: Optional anxiety tags override.
        seed: Optional random seed for reproducibility.

    Returns:
        Serialized ``PersonaProfile`` dict.
    """
    log = logger.bind(study_id=study_id, index=index)
    log.info("tool_generate_persona_start")

    agent = ConsumerGeneratorAgent()
    profile, state = agent.generate_single(
        study_id=study_id,
        index=index,
        life_stage=life_stage,
        anxieties=anxieties,
        seed=seed,
    )

    log.info(
        "tool_generate_persona_complete",
        persona_id=profile.persona_id,
        segment=profile.segment,
        authenticity_score=profile.authenticity_score,
        corrections=state.correction_count,
    )
    return profile.to_dict()


register_tool(
    generate_persona,
    spec=ToolSpec(
        name="generate_persona",
        description="生成单个虚拟消费者画像（四层模型+真实性评分）",
        parameters=[
            ToolParameter(name="study_id", type="string", description="研究标识", required=True),
            ToolParameter(name="index", type="integer", description="画像序号", required=True),
            ToolParameter(
                name="life_stage",
                type="string",
                description="人生阶段",
                required=False,
                default=None,
            ),
            ToolParameter(
                name="anxieties", type="array", description="焦虑标签", required=False, default=None
            ),
            ToolParameter(
                name="seed", type="integer", description="随机种子", required=False, default=None
            ),
        ],
        timeout_seconds=60.0,
        max_retries=1,
        retryable_errors=(ConnectionError, TimeoutError),
    ),
)


# ---------------------------------------------------------------------------
# Tool 2: generate_persona_batch
# ---------------------------------------------------------------------------


def generate_persona_batch(
    study_id: str,
    count: int,
    life_stages: list[str] | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    """Generate a batch of virtual consumer personas.

    Args:
        study_id: Parent study identifier.
        count: Number of personas to generate.
        life_stages: Optional list of life stages (rotated if fewer than count).
        seed: Optional base random seed.

    Returns:
        Dict with keys:
            - personas: list of serialized PersonaProfile dicts
            - summary: generation summary (counts, scores, corrections)
    """
    log = logger.bind(study_id=study_id, count=count)
    log.info("tool_generate_persona_batch_start")

    agent = ConsumerGeneratorAgent()
    profiles, states, summary = agent.generate_batch(
        study_id=study_id,
        count=count,
        life_stages=life_stages,
        seed=seed,
    )

    log.info(
        "tool_generate_persona_batch_complete",
        generated=len(profiles),
        passed=summary.get("passed_authenticity", 0),
    )

    return {
        "personas": [p.to_dict() for p in profiles],
        "summary": summary,
    }


register_tool(
    generate_persona_batch,
    spec=ToolSpec(
        name="generate_persona_batch",
        description="批量生成虚拟消费者画像",
        parameters=[
            ToolParameter(name="study_id", type="string", description="研究标识", required=True),
            ToolParameter(name="count", type="integer", description="生成数量", required=True),
            ToolParameter(
                name="life_stages",
                type="array",
                description="人生阶段列表",
                required=False,
                default=None,
            ),
            ToolParameter(
                name="seed", type="integer", description="随机种子", required=False, default=None
            ),
        ],
        timeout_seconds=300.0,
        max_retries=0,
    ),
)


# ---------------------------------------------------------------------------
# Tool 3: create_cbc_study
# ---------------------------------------------------------------------------


def create_cbc_study(
    study_id: str,
    product_category: str,
    research_goal: str,
    target_segments: list[str] | None = None,
    n_choice_sets: int = 12,
    n_alternatives: int = 3,
    algorithm: str = "d_optimal",
    include_none: bool = True,
    seed: int | None = None,
) -> dict[str, Any]:
    """Create a new CBC study definition.

    Uses the default dishwasher attribute set (7 attributes: price, brand,
    capacity, energy, spray_arm, installation, drying).

    Args:
        study_id: Unique study identifier.
        product_category: Product category (e.g. "洗碗机").
        research_goal: Research objective description.
        target_segments: Target consumer segments.
        n_choice_sets: Number of choice sets per respondent.
        n_alternatives: Number of alternatives per choice set (excl. none).
        algorithm: Design algorithm ("orthogonal" or "d_optimal").
        include_none: Whether to include a "none" option.
        seed: Random seed for reproducible designs.

    Returns:
        Serialized ``CBCStudy`` dict.
    """
    log = logger.bind(study_id=study_id)
    log.info("tool_create_study_start", algorithm=algorithm)

    from aicbc.questionnaire.models import DesignAlgorithm

    generator = QuestionnaireGenerator()
    study = generator.create_study(
        study_id=study_id,
        product_category=product_category,
        research_goal=research_goal,
        target_segments=target_segments or [],
        design_parameters=DesignParameters(
            n_choice_sets=n_choice_sets,
            n_alternatives=n_alternatives,
            algorithm=DesignAlgorithm(algorithm),
            include_none=include_none,
            seed=seed,
        ),
    )

    log.info(
        "tool_create_study_complete",
        n_attributes=len(study.attributes),
        n_choice_sets=n_choice_sets,
    )
    return study.model_dump(mode="json")


register_tool(
    create_cbc_study,
    spec=ToolSpec(
        name="create_cbc_study",
        description="创建CBC研究定义（含默认洗碗机6属性）",
        parameters=[
            ToolParameter(name="study_id", type="string", description="研究标识", required=True),
            ToolParameter(
                name="product_category", type="string", description="产品类别", required=True
            ),
            ToolParameter(
                name="research_goal", type="string", description="研究目标", required=True
            ),
            ToolParameter(
                name="target_segments",
                type="array",
                description="目标群体",
                required=False,
                default=None,
            ),
            ToolParameter(
                name="n_choice_sets",
                type="integer",
                description="选择集数量",
                required=False,
                default=12,
            ),
            ToolParameter(
                name="n_alternatives",
                type="integer",
                description="每集选项数",
                required=False,
                default=3,
            ),
            ToolParameter(
                name="algorithm",
                type="string",
                description="设计算法",
                required=False,
                default="d_optimal",
            ),
            ToolParameter(
                name="include_none",
                type="boolean",
                description="含none选项",
                required=False,
                default=True,
            ),
            ToolParameter(
                name="seed", type="integer", description="随机种子", required=False, default=None
            ),
        ],
        timeout_seconds=10.0,
        max_retries=0,
    ),
)


# ---------------------------------------------------------------------------
# Tool 4: generate_questionnaire
# ---------------------------------------------------------------------------


def generate_questionnaire(
    study: dict[str, Any],
    seed: int | None = None,
) -> dict[str, Any]:
    """Generate a CBC questionnaire from a study definition.

    Args:
        study: Serialized ``CBCStudy`` dict.
        seed: Optional random seed.

    Returns:
        Serialized ``CBCQuestionnaire`` dict.
    """
    log = logger.bind(study_id=study.get("study_id"))
    log.info("tool_generate_questionnaire_start")

    # Reconstruct CBCStudy from dict
    study_obj = CBCStudy.model_validate(study)

    generator = QuestionnaireGenerator()
    questionnaire = generator.generate_questionnaire(study=study_obj, seed=seed)

    log.info(
        "tool_generate_questionnaire_complete",
        d_efficiency=questionnaire.d_efficiency,
        n_choice_sets=len(questionnaire.choice_sets),
    )
    return questionnaire.model_dump(mode="json")


register_tool(
    generate_questionnaire,
    spec=ToolSpec(
        name="generate_questionnaire",
        description="生成CBC问卷（选择集）",
        parameters=[
            ToolParameter(
                name="study", type="object", description="CBCStudy序列化字典", required=True
            ),
            ToolParameter(
                name="seed", type="integer", description="随机种子", required=False, default=None
            ),
        ],
        timeout_seconds=120.0,
        max_retries=1,
        retryable_errors=(RuntimeError,),
    ),
)


# ---------------------------------------------------------------------------
# Tool 5: simulate_cbc_choices
# ---------------------------------------------------------------------------


def simulate_cbc_choices(
    persona: dict[str, Any],
    questionnaire: dict[str, Any],
    deterministic: bool = False,
    include_none: bool = False,
    seed: int | None = None,
) -> dict[str, Any]:
    """Simulate a persona's choices through a CBC questionnaire.

    Maps PersonaProfile traits to utility coefficients and selects
    alternatives using a multinomial logit model.

    Args:
        persona: Serialized ``PersonaProfile`` dict.
        questionnaire: Serialized ``CBCQuestionnaire`` dict.
        deterministic: If True, always pick max-utility option.
        include_none: If True, add a "none" option.
        seed: Optional random seed.

    Returns:
        Dict with keys:
            - raw_dataset: CBCRawDataset slice for this persona
            - persona_response: PersonaResponse dict
    """
    log = logger.bind(
        persona_id=persona.get("persona_id"),
        study_id=questionnaire.get("study_id"),
    )
    log.info("tool_simulate_choices_start")

    # Reconstruct objects
    persona_obj = PersonaProfile.model_validate(persona)
    from aicbc.questionnaire.models import CBCQuestionnaire as QModel

    q_obj = QModel.model_validate(questionnaire)

    # Reconstruct attributes from questionnaire metadata
    attrs = [Attribute.model_validate(a) for a in questionnaire.get("attributes", [])]
    if not attrs:
        # Fallback: extract from choice set alternatives
        first_cs = q_obj.choice_sets[0] if q_obj.choice_sets else None
        if first_cs:
            # This is a simplified fallback; full reconstruction requires study
            raise ValueError(
                "Questionnaire dict missing 'attributes' field; "
                "pass the full questionnaire with attribute definitions"
            )

    simulator = CBCChoiceSimulator(attributes=attrs)
    raw_dataset, persona_response = simulator.simulate(
        persona=persona_obj,
        questionnaire=q_obj,
        deterministic=deterministic,
        include_none=include_none,
        seed=seed,
    )

    log.info(
        "tool_simulate_choices_complete",
        n_choices=len(persona_response.responses),
        completion_status=persona_response.completion_status,
    )

    return {
        "raw_dataset": raw_dataset.to_dict(),
        "persona_response": persona_response.model_dump(mode="json"),
    }


register_tool(
    simulate_cbc_choices,
    spec=ToolSpec(
        name="simulate_cbc_choices",
        description="模拟单个画像的CBC选择行为",
        parameters=[
            ToolParameter(
                name="persona", type="object", description="PersonaProfile字典", required=True
            ),
            ToolParameter(
                name="questionnaire",
                type="object",
                description="CBCQuestionnaire字典",
                required=True,
            ),
            ToolParameter(
                name="deterministic",
                type="boolean",
                description="确定性选择",
                required=False,
                default=False,
            ),
            ToolParameter(
                name="include_none",
                type="boolean",
                description="含none选项",
                required=False,
                default=False,
            ),
            ToolParameter(
                name="seed", type="integer", description="随机种子", required=False, default=None
            ),
        ],
        timeout_seconds=10.0,
        max_retries=0,
    ),
)


# ---------------------------------------------------------------------------
# Tool 6: run_conjoint_analysis
# ---------------------------------------------------------------------------


def run_conjoint_analysis(
    dataset: dict[str, Any],
    attributes: list[dict[str, Any]],
    model_type: str = "auto",
    n_draws: int = 1000,
    n_tune: int = 1000,
    n_chains: int = 4,
) -> dict[str, Any]:
    """Run conjoint analysis on a CBCRawDataset.

    Auto-selects HB or MNL based on sample size. Wraps ``AnalysisAgent``.

    Args:
        dataset: Serialized ``CBCRawDataset`` dict.
        attributes: List of serialized ``Attribute`` dicts.
        model_type: "hb", "mnl", or "auto" (default: auto-select).
        n_draws: MCMC draws per chain (HB only).
        n_tune: MCMC tuning iterations (HB only).
        n_chains: Number of parallel chains (HB only).

    Returns:
        Dict with keys:
            - result: AnalysisResultResponse dict
            - report: AnalysisReport dict
            - diagnostics: raw convergence metrics
            - warnings: list of warning strings
    """
    log = logger.bind(
        study_id=dataset.get("metadata", {}).get("study_id"),
        model_type=model_type,
    )
    log.info("tool_run_analysis_start")

    # Reconstruct objects
    dataset_obj = CBCRawDataset.model_validate(dataset)
    attr_objs = [Attribute.model_validate(a) for a in attributes]

    # Build config
    config = AnalysisAgentConfig(
        hb_draws=n_draws,
        hb_tune=n_tune,
        hb_chains=n_chains,
    )

    # Override model selection if explicitly specified
    if model_type != "auto":
        config.min_resp_for_hb = 0 if model_type == "hb" else 999999

    agent = AnalysisAgent(config=config)
    result = agent.run(dataset=dataset_obj, attributes=attr_objs)

    log.info(
        "tool_run_analysis_complete",
        converged=result["result"].convergence.converged,
        rhat_max=result["result"].convergence.rhat_max,
        processing_time=result["result"].processing_time_seconds,
    )

    return {
        "result": result["result"].model_dump(mode="json"),
        "report": {
            "summary": result["report"].summary,
            "key_findings": result["report"].key_findings,
            "convergence_assessment": result["report"].convergence_assessment,
            "warnings": result["report"].warnings,
            "recommendations": result["report"].recommendations,
        },
        "diagnostics": result["diagnostics"],
        "warnings": result["warnings"],
    }


register_tool(
    run_conjoint_analysis,
    spec=ToolSpec(
        name="run_conjoint_analysis",
        description="运行联合分析（自动选择HB/MNL模型）",
        parameters=[
            ToolParameter(
                name="dataset", type="object", description="CBCRawDataset字典", required=True
            ),
            ToolParameter(
                name="attributes", type="array", description="属性定义列表", required=True
            ),
            ToolParameter(
                name="model_type",
                type="string",
                description="模型类型",
                required=False,
                default="auto",
            ),
            ToolParameter(
                name="n_draws",
                type="integer",
                description="MCMC采样数",
                required=False,
                default=1000,
            ),
            ToolParameter(
                name="n_tune",
                type="integer",
                description="调优迭代数",
                required=False,
                default=1000,
            ),
            ToolParameter(
                name="n_chains", type="integer", description="链数", required=False, default=4
            ),
        ],
        timeout_seconds=600.0,
        max_retries=1,
        retryable_errors=(RuntimeError,),
    ),
)


# ---------------------------------------------------------------------------
# Tool 7: batch_simulate_and_analyze
# ---------------------------------------------------------------------------


def batch_simulate_and_analyze(
    study: dict[str, Any],
    personas: list[dict[str, Any]],
    questionnaire: dict[str, Any] | None = None,
    deterministic: bool = False,
    seed: int | None = None,
    analysis_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """End-to-end batch simulation + analysis pipeline.

    Combines simulate + aggregate + analyze in one tool call.

    Args:
        study: Serialized ``CBCStudy`` dict (for attribute definitions).
        personas: List of serialized ``PersonaProfile`` dicts.
        questionnaire: Optional pre-generated questionnaire. If None, one is generated.
        deterministic: If True, use deterministic choice simulation.
        seed: Optional random seed.
        analysis_config: Optional analysis config overrides.

    Returns:
        Dict with keys:
            - questionnaire: Generated questionnaire dict
            - raw_dataset: Full CBCRawDataset dict
            - analysis_result: Analysis result dict
            - report: Natural-language report dict
            - summary: Pipeline summary (counts, costs, timing)
    """
    log = logger.bind(study_id=study.get("study_id"), n_personas=len(personas))
    log.info("tool_batch_pipeline_start")

    # Step 1: Generate questionnaire if not provided
    if questionnaire is None:
        questionnaire = generate_questionnaire(study=study, seed=seed)

    # Step 2: Simulate choices for all personas
    all_responses: list[dict[str, Any]] = []
    for i, persona in enumerate(personas):
        sim_result = simulate_cbc_choices(
            persona=persona,
            questionnaire=questionnaire,
            deterministic=deterministic,
            seed=(seed + i) if seed is not None else None,
        )
        all_responses.append(sim_result["persona_response"])

    # Step 3: Aggregate to CBCRawDataset
    from aicbc.tools.pipeline import responses_to_raw_dataset

    study_id = study.get("study_id", "unknown")
    attrs = study.get("attributes", [])
    raw_dataset = responses_to_raw_dataset(
        responses=all_responses,
        study_id=study_id,
        attributes=attrs,
        questionnaire=questionnaire,
    )

    # Step 4: Run analysis
    analysis_cfg = analysis_config or {}
    analysis_result = run_conjoint_analysis(
        dataset=raw_dataset,
        attributes=attrs,
        model_type=analysis_cfg.get("model_type", "auto"),
        n_draws=analysis_cfg.get("n_draws", 1000),
        n_tune=analysis_cfg.get("n_tune", 1000),
        n_chains=analysis_cfg.get("n_chains", 4),
    )

    log.info(
        "tool_batch_pipeline_complete",
        n_personas=len(personas),
        n_choices=len(all_responses) * len(questionnaire.get("choice_sets", [])),
    )

    return {
        "questionnaire": questionnaire,
        "raw_dataset": raw_dataset,
        "analysis_result": analysis_result["result"],
        "report": analysis_result["report"],
        "diagnostics": analysis_result["diagnostics"],
        "warnings": analysis_result["warnings"],
        "summary": {
            "n_personas": len(personas),
            "n_choice_sets": len(questionnaire.get("choice_sets", [])),
            "model_type": analysis_result["result"].get("model_type", "unknown"),
            "converged": analysis_result["result"].get("convergence", {}).get("converged", False),
            "processing_time_seconds": analysis_result["result"].get("processing_time_seconds", 0),
        },
    }


register_tool(
    batch_simulate_and_analyze,
    spec=ToolSpec(
        name="batch_simulate_and_analyze",
        description="端到端批量模拟+分析流水线",
        parameters=[
            ToolParameter(name="study", type="object", description="CBCStudy字典", required=True),
            ToolParameter(name="personas", type="array", description="画像列表", required=True),
            ToolParameter(
                name="questionnaire",
                type="object",
                description="预生成问卷",
                required=False,
                default=None,
            ),
            ToolParameter(
                name="deterministic",
                type="boolean",
                description="确定性选择",
                required=False,
                default=False,
            ),
            ToolParameter(
                name="seed", type="integer", description="随机种子", required=False, default=None
            ),
            ToolParameter(
                name="analysis_config",
                type="object",
                description="分析配置",
                required=False,
                default=None,
            ),
        ],
        timeout_seconds=900.0,
        max_retries=0,
    ),
)
