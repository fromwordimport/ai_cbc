"""CBC questionnaire API routes — study management and design generation."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from aicbc.api.schemas import (
    CreateStudyRequest,
    GenerateQuestionnaireResponse,
    QuestionnaireDetailResponse,
    StudyDetailResponse,
    StudyListResponse,
    StudySummary,
)
from aicbc.core.store import QuestionnaireStore, get_questionnaire_store
from aicbc.questionnaire.generator import QuestionnaireGenerator
from aicbc.questionnaire.models import StudyStatus
from aicbc.questionnaire.validators import QuestionnaireValidator

router = APIRouter()
logger = structlog.get_logger("aicbc.api.questionnaires")


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
    generator = QuestionnaireGenerator()
    study = generator.create_study(
        study_id=request.study_id,
        product_category=request.product_category,
        research_goal=request.research_goal,
        target_segments=request.target_segments,
    )
    store.save_study(study)
    logger.info("study_created", study_id=study.study_id)
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
    items, total = store.list_studies(
        product_category=product_category,
        page=page,
        page_size=page_size,
    )
    return StudyListResponse(
        total=total,
        page=page,
        page_size=page_size,
        studies=[StudySummary.from_study(s) for s in items],
    )


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
    study = store.get_study(study_id)
    if study is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Study '{study_id}' not found",
        )
    return StudyDetailResponse.from_study(study)


@router.delete(
    "/studies/{study_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a study",
)
async def delete_study(
    study_id: str,
    store: QuestionnaireStore = Depends(get_questionnaire_store),
) -> None:
    """Delete a study and its associated questionnaire."""
    deleted = store.delete_study(study_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Study '{study_id}' not found",
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
    study = store.get_study(study_id)
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
    store.save_study(study)
    store.save_questionnaire(questionnaire)

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
    questionnaire = store.get_questionnaire(study_id)
    if questionnaire is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No questionnaire found for study '{study_id}'",
        )
    return QuestionnaireDetailResponse.from_questionnaire(questionnaire)
