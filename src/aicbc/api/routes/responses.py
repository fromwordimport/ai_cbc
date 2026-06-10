"""Response simulation API routes — let virtual consumers answer CBC questionnaires."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, status

from aicbc.api.schemas import (
    PersonaResponseSummary,
    RawDatasetExportResponse,
    SimulatedResponseSummary,
    SimulateResponsesRequest,
    SimulateResponsesResponse,
)
from aicbc.core.simulation.cbc_choice_simulator import CBCChoiceSimulator
from aicbc.core.simulation.llm_choice_simulator import LLMChoiceSimulator
from aicbc.core.store import (
    PersonaStore,
    ResponseStore,
    get_questionnaire_store,
    get_response_store,
    get_store,
)
from aicbc.questionnaire.response_models import CBCRawDataset, DatasetMetadata

router = APIRouter()
logger = structlog.get_logger("aicbc.api.responses")


@router.post(
    "/studies/{study_id}/simulate-responses",
    response_model=SimulateResponsesResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Simulate persona responses for a study",
    response_description="Batch simulation results",
)
async def simulate_responses(
    study_id: str,
    request: SimulateResponsesRequest,
    persona_store: PersonaStore = Depends(get_store),
    questionnaire_store=Depends(get_questionnaire_store),
    response_store: ResponseStore = Depends(get_response_store),
) -> SimulateResponsesResponse:
    """Run the CBC questionnaire for a batch of personas.

    Each persona answers every choice set in the questionnaire.  Results are
    stored as both individual PersonaResponse records and an aggregated
    CBCRawDataset.
    """
    questionnaire = questionnaire_store.get_questionnaire(study_id)
    if questionnaire is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No questionnaire found for study '{study_id}'",
        )

    study = questionnaire_store.get_study(study_id)
    if study is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Study '{study_id}' not found",
        )

    log = logger.bind(
        study_id=study_id,
        n_personas=len(request.persona_ids),
        mode=request.mode,
    )
    log.info("batch_simulation_start")

    # Select simulator based on mode
    if request.mode == "llm":
        simulator: CBCChoiceSimulator | LLMChoiceSimulator = LLMChoiceSimulator(
            attributes=study.attributes,
        )
    else:
        simulator = CBCChoiceSimulator(attributes=study.attributes)

    summaries: list[SimulatedResponseSummary] = []
    failed = 0
    all_records: list = []

    for idx, persona_id in enumerate(request.persona_ids):
        persona = persona_store.get(persona_id)
        if persona is None:
            log.warning("persona_not_found", persona_id=persona_id)
            failed += 1
            continue

        try:
            if request.mode == "llm":
                raw_slice, persona_response = simulator.simulate(
                    persona=persona,
                    questionnaire=questionnaire,
                    seed=(request.seed + idx) if request.seed is not None else None,
                )
            else:
                raw_slice, persona_response = simulator.simulate(
                    persona=persona,
                    questionnaire=questionnaire,
                    deterministic=request.deterministic,
                    seed=(request.seed + idx) if request.seed is not None else None,
                )
        except Exception as exc:
            log.error("simulation_failed", persona_id=persona_id, error=str(exc))
            failed += 1
            continue

        # Fix respondent_index in the slice
        for record in raw_slice.choice_records:
            record.respondent_index = idx

        all_records.extend(raw_slice.choice_records)
        response_store.save_response(persona_response)

        summaries.append(SimulatedResponseSummary(
            persona_id=persona_id,
            response_id=persona_response.response_id,
            completion_status=persona_response.completion_status,
            n_choice_sets_answered=len(persona_response.responses),
        ))

    # Merge into a single dataset
    if all_records:
        dataset = CBCRawDataset(
            metadata=DatasetMetadata(
                study_id=study_id,
                n_respondents=len(summaries),
                n_choice_sets=questionnaire.design_parameters.n_choice_sets,
                n_alternatives=questionnaire.design_parameters.n_alternatives,
            ),
            choice_records=all_records,
        )
        response_store.save_dataset(study_id, dataset)

    log.info(
        "batch_simulation_complete",
        simulated=len(summaries),
        failed=failed,
    )

    return SimulateResponsesResponse(
        study_id=study_id,
        questionnaire_id=questionnaire.questionnaire_id,
        simulated=len(summaries),
        failed=failed,
        summaries=summaries,
    )


@router.get(
    "/studies/{study_id}/responses",
    response_model=list[PersonaResponseSummary],
    summary="List simulated responses for a study",
)
async def list_responses(
    study_id: str,
    response_store: ResponseStore = Depends(get_response_store),
) -> list[PersonaResponseSummary]:
    """List all persona responses recorded for a study."""
    items, _ = response_store.list_responses_by_study(study_id)
    return [
        PersonaResponseSummary(
            response_id=r.response_id,
            persona_id=r.persona_id,
            completion_status=r.completion_status,
            n_answers=len(r.responses),
            created_at=r.created_at,
        )
        for r in items
    ]


@router.get(
    "/studies/{study_id}/responses/export",
    response_model=RawDatasetExportResponse,
    summary="Export CBCRawDataset for a study",
)
async def export_dataset(
    study_id: str,
    response_store: ResponseStore = Depends(get_response_store),
) -> RawDatasetExportResponse:
    """Export the aggregated CBCRawDataset for downstream analysis."""
    dataset = response_store.get_dataset(study_id)
    if dataset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No response dataset found for study '{study_id}'",
        )

    return RawDatasetExportResponse(
        study_id=dataset.metadata.study_id,
        n_respondents=dataset.metadata.n_respondents,
        n_choice_sets=dataset.metadata.n_choice_sets,
        n_alternatives=dataset.metadata.n_alternatives,
        n_total_records=len(dataset.choice_records),
        choice_records=[
            record.model_dump(mode="json") for record in dataset.choice_records
        ],
    )
