"""CBC questionnaire API routes — study management and design generation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError

from aicbc.analysis.store import AnalysisStore, get_analysis_store
from aicbc.api.schemas import (
    CreateStudyRequest,
    GenerateQuestionnaireResponse,
    QuestionnaireDetailResponse,
    StudyDesignResponse,
    StudyDetailResponse,
    StudyExportResponse,
    StudyListResponse,
    StudySummary,
    StudyUpdateRequest,
    UpdateStudyDesignRequest,
)
from aicbc.core.cache import (
    get_studies_list_cache,
    invalidate_dashboard_summary,
    invalidate_personas_list,
    invalidate_studies_list,
)
from aicbc.core.privacy import redact_dict
from aicbc.core.security.input_sanitizer import sanitize_id
from aicbc.core.store import (
    PersonaStore,
    QuestionnaireStore,
    ResponseStore,
    get_questionnaire_store,
    get_response_store,
    get_store,
)
from aicbc.questionnaire.generator import QuestionnaireGenerator
from aicbc.questionnaire.models import (
    Attribute,
    AttributeLevel,
    Condition,
    DesignParameters,
    ProhibitedPair,
    StudyStatus,
)
from aicbc.questionnaire.validators import QuestionnaireValidator

router = APIRouter()
logger = structlog.get_logger("aicbc.api.questionnaires")


def parse_custom_attributes(raw: list[dict] | None) -> list[Attribute] | None:
    """Parse custom attributes from request payload."""
    if raw is None:
        return None
    attrs: list[Attribute] = []
    for item in raw:
        levels_raw = item.get("levels", [])
        levels = [
            AttributeLevel(
                value=lv["value"],
                label=lv.get("label", str(lv["value"])),
                description=lv.get("description"),
            )
            for lv in levels_raw
        ]
        attrs.append(Attribute(
            id=item["id"],
            name=item.get("name", item["id"]),
            type=item.get("type") or "categorical",
            levels=levels,
            description=item.get("description"),
        ))
    return attrs


def parse_prohibited_pairs(raw: list[dict] | None) -> list[ProhibitedPair]:
    """Parse raw prohibited pairs into ProhibitedPair objects."""
    if not raw:
        return []
    result: list[ProhibitedPair] = []
    for item in raw:
        conditions = item.get("conditions", [])
        parsed_conditions = [
            Condition(attribute_id=c["attribute_id"], level_value=c["level_value"])
            for c in conditions
        ]
        result.append(ProhibitedPair(conditions=parsed_conditions))
    return result


def _parse_design_params(raw: dict | None) -> DesignParameters | None:
    """Parse custom design parameters from request payload."""
    if raw is None:
        return None
    return DesignParameters(**raw)


# ---------------------------------------------------------------------------
# Study management
# ---------------------------------------------------------------------------


@router.post(
    "/studies",
    response_model=StudyDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new CBC study",
    response_description="Created study definition",
)
async def create_study(
    request: CreateStudyRequest,
    store: QuestionnaireStore = Depends(get_questionnaire_store),
) -> StudyDetailResponse:
    """Create a new CBC study with product attributes and design parameters."""
    # Sanitize study_id
    safe_study_id = sanitize_id(request.study_id, field_name="study_id")

    # Conflict detection: reject duplicate study_id
    if await store.aget_study(safe_study_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Study '{safe_study_id}' already exists",
        )

    attributes = parse_custom_attributes(request.attributes)
    design_params = _parse_design_params(request.design_parameters)

    generator = QuestionnaireGenerator()
    study = generator.create_study(
        study_id=safe_study_id,
        product_category=request.product_category,
        research_goal=request.research_goal,
        attributes=attributes,
        design_parameters=design_params,
        target_segments=request.target_segments,
    )
    await store.asave_study(study)
    invalidate_studies_list()
    invalidate_dashboard_summary()
    logger.info("study_created", study_id=study.study_id, n_attributes=len(study.attributes))
    return StudyDetailResponse.from_study(study)


@router.get(
    "/studies",
    response_model=StudyListResponse,
    summary="List CBC studies",
    response_description="Paginated list of studies",
)
async def list_studies(
    product_category: str | None = Query(None, description="Filter by product category"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    store: QuestionnaireStore = Depends(get_questionnaire_store),
) -> StudyListResponse:
    """List all CBC studies with optional filtering."""
    cache = get_studies_list_cache()
    cache_key = ("list", product_category, page, page_size)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    items, total = await store.alist_studies(
        product_category=product_category,
        page=page,
        page_size=page_size,
    )
    response = StudyListResponse(
        total=total,
        page=page,
        page_size=page_size,
        studies=[StudySummary.from_study(s) for s in items],
    )
    cache.set(cache_key, response)
    return response


@router.get(
    "/studies/{study_id}",
    response_model=StudyDetailResponse,
    summary="Get a study by ID",
    response_description="Full study definition",
)
async def get_study(
    study_id: str,
    store: QuestionnaireStore = Depends(get_questionnaire_store),
) -> StudyDetailResponse:
    """Retrieve a complete CBC study definition."""
    study = await store.aget_study(study_id)
    if study is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Study '{study_id}' not found",
        )
    return StudyDetailResponse.from_study(study)


@router.put(
    "/studies/{study_id}",
    response_model=StudyDetailResponse,
    summary="Update a study",
    response_description="Updated study definition",
)
async def update_study(
    study_id: str,
    request: StudyUpdateRequest,
    store: QuestionnaireStore = Depends(get_questionnaire_store),
) -> StudyDetailResponse:
    """Update an existing CBC study's configuration."""
    study = await store.aget_study(study_id)
    if study is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Study '{study_id}' not found",
        )

    updates = request.model_dump(exclude_none=True)
    for field, value in updates.items():
        if field == "design_parameters" and value is not None:
            for dp_field, dp_value in value.items():
                setattr(study.design_parameters, dp_field, dp_value)
        elif hasattr(study, field):
            setattr(study, field, value)

    await store.asave_study(study)
    invalidate_studies_list()
    invalidate_dashboard_summary()
    logger.info("study_updated", study_id=study_id)
    return StudyDetailResponse.from_study(study)


@router.delete(
    "/studies/{study_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete a study",
)
async def delete_study(
    study_id: str,
    store: QuestionnaireStore = Depends(get_questionnaire_store),
    persona_store: PersonaStore = Depends(get_store),
    response_store: ResponseStore = Depends(get_response_store),
    analysis_store: AnalysisStore = Depends(get_analysis_store),
) -> None:
    """Delete a study and cascade-delete all derived artefacts."""
    study = await store.aget_study(study_id)
    if study is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Study '{study_id}' not found",
        )

    # Cascade delete in dependency order: analyses → responses → personas → study.
    await analysis_store.adelete_by_study(study_id)
    await response_store.adelete_by_study(study_id)
    await persona_store.adelete_by_study(study_id)
    await store.adelete_study(study_id)

    invalidate_studies_list()
    invalidate_dashboard_summary()
    invalidate_personas_list()

    logger.info("study_deleted_cascade", study_id=study_id)


# ---------------------------------------------------------------------------
# Data subject rights — export
# ---------------------------------------------------------------------------


@router.get(
    "/studies/{study_id}/export",
    response_model=StudyExportResponse,
    summary="Export all study data",
    response_description="Complete study data including personas, responses and analyses",
)
async def export_study(
    study_id: str,
    store: QuestionnaireStore = Depends(get_questionnaire_store),
    persona_store: PersonaStore = Depends(get_store),
    response_store: ResponseStore = Depends(get_response_store),
    analysis_store: AnalysisStore = Depends(get_analysis_store),
) -> StudyExportResponse:
    """Export all data held for a study.

    Returns the study definition, questionnaire, personas, simulated responses,
    raw dataset and analysis results in a portable JSON structure suitable for
    data-subject access / portability requests.
    """
    study = await store.aget_study(study_id)
    if study is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Study '{study_id}' not found",
        )

    questionnaire = await store.aget_questionnaire(study_id)

    personas, _ = await persona_store.alist_all(study_id=study_id, page=1, page_size=10_000)
    responses, _ = await response_store.alist_responses_by_study(study_id, page=1, page_size=10_000)
    dataset = await response_store.aget_dataset(study_id)
    analyses = await analysis_store.alist_jobs_by_study(study_id)

    return StudyExportResponse(
        study_id=study_id,
        exported_at=datetime.now(UTC),
        study=redact_dict(study.model_dump(mode="json")),
        questionnaire=redact_dict(questionnaire.model_dump(mode="json")) if questionnaire else None,
        personas=[redact_dict(p.model_dump(mode="json")) for p in personas],
        responses=[redact_dict(r.model_dump(mode="json")) for r in responses],
        dataset=redact_dict(dataset.model_dump(mode="json")) if dataset else None,
        analyses=[redact_dict(a.model_dump(mode="json")) for a in analyses],
    )


# ---------------------------------------------------------------------------
# Questionnaire generation
# ---------------------------------------------------------------------------


@router.post(
    "/studies/{study_id}/generate",
    response_model=GenerateQuestionnaireResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a questionnaire for a study",
    response_description="Generated questionnaire with efficiency metrics",
)
async def generate_questionnaire(
    study_id: str,
    seed: int | None = Query(None, description="Optional random seed for reproducibility"),
    store: QuestionnaireStore = Depends(get_questionnaire_store),
) -> GenerateQuestionnaireResponse:
    """Generate a CBC questionnaire using the study's design parameters.

    The algorithm (orthogonal or D-optimal) is determined by the study's
    design_parameters.algorithm field. D-efficiency is reported for quality
    validation (target >= 0.85).
    """
    study = await store.aget_study(study_id)
    if study is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Study '{study_id}' not found",
        )

    log = logger.bind(study_id=study_id)
    log.info("questionnaire_generation_requested", algorithm=study.design_parameters.algorithm.value)

    generator = QuestionnaireGenerator()
    questionnaire = generator.generate_questionnaire(study, seed=seed)

    # Run quality validation
    validator = QuestionnaireValidator()
    validation = validator.validate(questionnaire)

    # Update study status
    study.status = StudyStatus.READY
    await store.asave_study(study)
    await store.asave_questionnaire(questionnaire)
    invalidate_studies_list()
    invalidate_dashboard_summary()

    log.info(
        "questionnaire_generated",
        d_efficiency=questionnaire.d_efficiency,
        validation_passed=validation.passed,
    )

    return GenerateQuestionnaireResponse(
        study_id=study_id,
        questionnaire_id=questionnaire.questionnaire_id,
        algorithm=study.design_parameters.algorithm.value,
        d_efficiency=questionnaire.d_efficiency,
        a_efficiency=questionnaire.a_efficiency,
        n_choice_sets=len(questionnaire.choice_sets),
        n_alternatives=study.design_parameters.n_alternatives,
        include_none=study.design_parameters.include_none,
        validation_passed=validation.passed,
        validation_errors=validation.errors,
    )


@router.get(
    "/studies/{study_id}/questionnaire",
    response_model=QuestionnaireDetailResponse,
    summary="Get the generated questionnaire",
    response_description="Full questionnaire with choice sets",
)
async def get_questionnaire(
    study_id: str,
    store: QuestionnaireStore = Depends(get_questionnaire_store),
) -> QuestionnaireDetailResponse:
    """Retrieve the questionnaire generated for a study."""
    questionnaire = await store.aget_questionnaire(study_id)
    if questionnaire is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No questionnaire found for study '{study_id}'",
        )
    return QuestionnaireDetailResponse.from_questionnaire(questionnaire)


# ---------------------------------------------------------------------------
# Study attribute design
# ---------------------------------------------------------------------------


@router.get(
    "/studies/{study_id}/design",
    response_model=StudyDesignResponse,
    summary="Get study attribute design",
    response_description="Study attributes design",
)
async def get_study_design(
    study_id: str,
    store: QuestionnaireStore = Depends(get_questionnaire_store),
) -> StudyDesignResponse:
    """Retrieve the attribute design of a CBC study."""
    study = await store.aget_study(study_id)
    if study is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Study '{study_id}' not found",
        )
    return StudyDesignResponse(
        study_id=study_id,
        attributes=[a.model_dump(mode="json") for a in study.attributes],
        prohibited_pairs=[
            {
                "conditions": [
                    {"attribute_id": c.attribute_id, "level_value": c.level_value}
                    for c in pair.conditions
                ]
            }
            for pair in study.prohibited_pairs
        ],
    )


@router.put(
    "/studies/{study_id}/design",
    response_model=StudyDesignResponse,
    summary="Update study attribute design",
    response_description="Updated study attributes design",
)
async def update_study_design(
    study_id: str,
    request: UpdateStudyDesignRequest,
    store: QuestionnaireStore = Depends(get_questionnaire_store),
) -> StudyDesignResponse:
    """Update the attributes of a CBC study."""
    study = await store.aget_study(study_id)
    if study is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Study '{study_id}' not found",
        )

    # Parse raw dicts into Attribute objects (triggers Attribute-level validators)
    try:
        attributes = parse_custom_attributes(request.attributes)
    except ValidationError as exc:
        logger.warning(
            "study_design_validation_failed",
            study_id=study_id,
            errors=exc.errors(),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid attribute data: {exc.errors()}",
        ) from exc

    if attributes is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="attributes cannot be null",
        )

    # Additional validation: at least 2 attributes
    if len(attributes) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CBC study must have at least 2 attributes",
        )

    # Additional validation: unique attribute ids
    ids = [attr.id for attr in attributes]
    if len(ids) != len(set(ids)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="attribute ids must be unique",
        )

    # Additional validation: level values non-empty
    for attr in attributes:
        for lv in attr.levels:
            if lv.value is None or (
                isinstance(lv.value, str) and lv.value.strip() == ""
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"level value cannot be empty for attribute '{attr.id}'",
                )

    # Parse and validate prohibited pairs
    prohibited_pairs = parse_prohibited_pairs(request.prohibited_pairs)
    valid_attr_ids = {attr.id for attr in attributes}
    valid_levels: dict[str, set[Any]] = {
        attr.id: {lv.value for lv in attr.levels} for attr in attributes
    }

    for pair in prohibited_pairs:
        if len(pair.conditions) < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="each prohibited pair must contain at least 2 conditions",
            )

        pair_attr_ids = [c.attribute_id for c in pair.conditions]
        if len(pair_attr_ids) != len(set(pair_attr_ids)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="duplicate attribute_ids are not allowed within a prohibited pair",
            )

        for cond in pair.conditions:
            if cond.attribute_id not in valid_attr_ids:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"attribute_id '{cond.attribute_id}' in prohibited pair does not exist",
                )

            if cond.level_value not in valid_levels.get(cond.attribute_id, set()):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"level_value '{cond.level_value}' for attribute '{cond.attribute_id}' in prohibited pair is invalid",
                )

    # Update study
    study.attributes = attributes
    study.prohibited_pairs = prohibited_pairs
    if study.status in (StudyStatus.INIT, StudyStatus.READY):
        study.status = StudyStatus.DESIGNING

    await store.asave_study(study)
    invalidate_studies_list()
    invalidate_dashboard_summary()
    logger.info(
        "study_design_updated",
        study_id=study_id,
        n_attributes=len(attributes),
    )

    return StudyDesignResponse(
        study_id=study_id,
        attributes=[a.model_dump(mode="json") for a in study.attributes],
        prohibited_pairs=[
            {
                "conditions": [
                    {"attribute_id": c.attribute_id, "level_value": c.level_value}
                    for c in pair.conditions
                ]
            }
            for pair in study.prohibited_pairs
        ],
    )
