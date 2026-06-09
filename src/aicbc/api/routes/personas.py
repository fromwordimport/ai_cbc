"""Persona generation and management API routes."""

from __future__ import annotations

import time

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from aicbc.api.dependencies import (
    get_authenticity_scorer,
    get_bias_auditor,
    get_logic_validator,
    get_profile_generator,
    get_schema_validator,
    get_seed_generator,
)
from aicbc.api.schemas import (
    BatchGenerateRequest,
    BatchGenerateResponse,
    GenerationErrorDetail,
    LayerResponse,
    PersonaDetail,
    PersonaListResponse,
    PersonaSummary,
    ValidateResponse,
)
from aicbc.core.scoring.authenticity_scorer import AuthenticityScorer
from aicbc.core.scoring.bias_auditor import BiasAuditor
from aicbc.core.store import PersonaStore, get_store
from aicbc.core.validators import LogicValidator, SchemaValidator
from aicbc.generators.profile_generator import ProfileGenerator
from aicbc.generators.seed_generator import SeedGenerator

router = APIRouter()
logger = structlog.get_logger("aicbc.api.personas")


# ---------------------------------------------------------------------------
# Batch generation
# ---------------------------------------------------------------------------


@router.post(
    "/personas/generate",
    response_model=BatchGenerateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a batch of virtual consumer personas",
    response_description="Batch generation results with generated personas and any errors",
)
async def generate_personas_batch(
    request: BatchGenerateRequest,
    seed_gen: SeedGenerator = Depends(get_seed_generator),
    profile_gen: ProfileGenerator = Depends(get_profile_generator),
    schema_validator: SchemaValidator = Depends(get_schema_validator),
    logic_validator: LogicValidator = Depends(get_logic_validator),
    authenticity_scorer: AuthenticityScorer = Depends(get_authenticity_scorer),
    bias_auditor: BiasAuditor = Depends(get_bias_auditor),
    store: PersonaStore = Depends(get_store),
) -> BatchGenerateResponse:
    """Generate a batch of virtual consumer personas.

    Each persona flows through:
        SeedGenerator → ProfileGenerator → (optional) Validation → Store

    Generation is synchronous; for large batches (>50) consider calling
    this endpoint multiple times with smaller counts.
    """
    log = logger.bind(study_id=request.study_id, count=request.count)
    log.info("batch_generation_start")

    start_time = time.perf_counter()
    personas: list[PersonaSummary] = []
    errors: list[GenerationErrorDetail] = []
    total_cost = 0.0

    # Fix seed for reproducibility if provided
    if request.seed is not None:
        seed_gen = SeedGenerator(seed=request.seed)

    # Sanitize study_id for persona_id pattern compliance
    safe_study_id = request.study_id.replace("-", "_")
    for i in range(request.count):
        persona_id = f"persona-{safe_study_id}-{i + 1:03d}"
        try:
            seed = seed_gen.generate_seed()
            profile = profile_gen.generate(persona_id, seed)

            if not request.skip_validation:
                schema_result = schema_validator.validate(profile)
                logic_result = logic_validator.validate(profile)
                if not (schema_result.passed and logic_result.passed):
                    # Log but still store — caller can decide action
                    log.warning(
                        "persona_validation_failed",
                        persona_id=persona_id,
                        schema_errors=schema_result.errors,
                        logic_errors=logic_result.errors,
                    )

            # Run authenticity scoring and bias audit
            auth_result = authenticity_scorer.score(profile)
            profile.authenticity_score = auth_result.total_score

            bias_result = bias_auditor.audit(profile)
            profile.bias_audit_status = bias_result.status

            store.save(profile)
            personas.append(PersonaSummary.from_profile(profile))
            total_cost += profile.generation_metadata.cost_cny

        except Exception as exc:
            log.error("persona_generation_failed", index=i, error=str(exc))
            errors.append(GenerationErrorDetail(index=i, error=str(exc)))

    elapsed = round(time.perf_counter() - start_time, 3)
    log.info(
        "batch_generation_complete",
        generated=len(personas),
        failed=len(errors),
        cost_cny=round(total_cost, 4),
        elapsed_seconds=elapsed,
    )

    return BatchGenerateResponse(
        study_id=request.study_id,
        requested=request.count,
        generated=len(personas),
        failed=len(errors),
        personas=personas,
        errors=errors,
        total_cost_cny=round(total_cost, 4),
        generation_time_seconds=elapsed,
    )


# ---------------------------------------------------------------------------
# Persona retrieval
# ---------------------------------------------------------------------------


@router.get(
    "/personas/{persona_id}",
    response_model=PersonaDetail,
    summary="Get a persona by ID",
    response_description="Full persona profile detail",
)
async def get_persona(
    persona_id: str,
    store: PersonaStore = Depends(get_store),
) -> PersonaDetail:
    """Retrieve a complete persona profile by its unique ID."""
    profile = store.get(persona_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Persona '{persona_id}' not found",
        )
    return PersonaDetail.from_profile(profile)


@router.get(
    "/personas",
    response_model=PersonaListResponse,
    summary="List personas with optional filters",
    response_description="Paginated list of persona summaries",
)
async def list_personas(
    study_id: str | None = Query(None, description="Filter by study ID prefix"),
    segment: str | None = Query(None, description="Filter by segment substring"),
    city_tier: str | None = Query(None, description="Filter by city tier substring"),
    bias_status: str | None = Query(None, description="Filter by bias audit status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    store: PersonaStore = Depends(get_store),
) -> PersonaListResponse:
    """List stored personas with optional filtering and pagination."""
    items, total = store.list_all(
        study_id=study_id,
        segment=segment,
        city_tier=city_tier,
        bias_status=bias_status,
        page=page,
        page_size=page_size,
    )

    return PersonaListResponse(
        total=total,
        page=page,
        page_size=page_size,
        personas=[PersonaSummary.from_profile(p) for p in items],
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@router.post(
    "/personas/{persona_id}/validate",
    response_model=ValidateResponse,
    summary="Validate a stored persona",
    response_description="Schema and logic validation results",
)
async def validate_persona(
    persona_id: str,
    store: PersonaStore = Depends(get_store),
    schema_validator: SchemaValidator = Depends(get_schema_validator),
    logic_validator: LogicValidator = Depends(get_logic_validator),
) -> ValidateResponse:
    """Run schema and logic validators against a stored persona.

    This is useful for re-validating personas after manual edits or
    when validation rules have been updated.
    """
    profile = store.get(persona_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Persona '{persona_id}' not found",
        )

    schema_result = schema_validator.validate(profile)
    logic_result = logic_validator.validate(profile)

    return ValidateResponse.from_results(persona_id, schema_result, logic_result)


# ---------------------------------------------------------------------------
# Layer access
# ---------------------------------------------------------------------------


@router.get(
    "/personas/{persona_id}/layers/{layer_number}",
    response_model=LayerResponse,
    summary="Get a specific layer of a persona",
    response_description="Layer data with metadata",
)
async def get_persona_layer(
    persona_id: str,
    layer_number: int,
    store: PersonaStore = Depends(get_store),
) -> LayerResponse:
    """Retrieve a specific layer (1-4) of a persona profile."""
    profile = store.get(persona_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Persona '{persona_id}' not found",
        )

    if layer_number not in (1, 2, 3, 4):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"layer_number must be 1-4, got {layer_number}",
        )

    layer = profile.get_layer(layer_number)
    layer_names = {
        1: "demographics",
        2: "behavior",
        3: "psychology",
        4: "scenarios",
    }

    return LayerResponse(
        persona_id=persona_id,
        layer_number=layer_number,
        layer_name=layer_names[layer_number],
        data=layer.model_dump(mode="json"),
    )


# ---------------------------------------------------------------------------
# Deletion (admin/testing)
# ---------------------------------------------------------------------------


@router.delete(
    "/personas/{persona_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a persona",
)
async def delete_persona(
    persona_id: str,
    store: PersonaStore = Depends(get_store),
) -> None:
    """Delete a persona from the store."""
    deleted = store.delete(persona_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Persona '{persona_id}' not found",
        )
