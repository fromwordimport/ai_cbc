"""Behavior simulation API routes — conversation and purchase decision."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, status

from aicbc.api.dependencies import get_behavior_simulator
from aicbc.api.schemas import (
    ConverseRequest,
    ConverseResponse,
    InterviewRequest,
    InterviewResponse,
    PurchaseDecisionRequest,
    PurchaseDecisionResponse,
)
from aicbc.core.simulation.behavior_simulator import BehaviorSimulator
from aicbc.core.store import PersonaStore, get_store

router = APIRouter()
logger = structlog.get_logger("aicbc.api.simulations")


# ---------------------------------------------------------------------------
# Mode A: Conversational research
# ---------------------------------------------------------------------------


@router.post(
    "/personas/{persona_id}/converse",
    response_model=ConverseResponse,
    summary="Simulate a single conversational turn",
    response_description="Consumer response to the researcher's question",
)
async def converse(
    persona_id: str,
    request: ConverseRequest,
    store: PersonaStore = Depends(get_store),
    simulator: BehaviorSimulator = Depends(get_behavior_simulator),
) -> ConverseResponse:
    """Generate a single conversational turn with a virtual consumer."""
    profile = store.get(persona_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Persona '{persona_id}' not found",
        )

    turn = simulator.converse(
        persona=profile,
        researcher_question=request.question,
        context=request.context or None,
    )

    return ConverseResponse(
        persona_id=persona_id,
        turn_number=turn.turn_number,
        researcher_question=turn.researcher_question,
        consumer_response=turn.consumer_response,
        emotion_tag=turn.emotion_tag,
        inconsistency_flag=turn.inconsistency_flag,
    )


@router.post(
    "/personas/{persona_id}/interview",
    response_model=InterviewResponse,
    summary="Run a multi-question interview",
    response_description="All conversational turns",
)
async def run_interview(
    persona_id: str,
    request: InterviewRequest,
    store: PersonaStore = Depends(get_store),
    simulator: BehaviorSimulator = Depends(get_behavior_simulator),
) -> InterviewResponse:
    """Run a structured interview with multiple questions."""
    profile = store.get(persona_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Persona '{persona_id}' not found",
        )

    turns = simulator.run_interview(
        persona=profile,
        questions=request.questions,
        context=request.context or None,
    )

    return InterviewResponse(
        persona_id=persona_id,
        turns=[
            ConverseResponse(
                persona_id=persona_id,
                turn_number=t.turn_number,
                researcher_question=t.researcher_question,
                consumer_response=t.consumer_response,
                emotion_tag=t.emotion_tag,
                inconsistency_flag=t.inconsistency_flag,
            )
            for t in turns
        ],
        total_turns=len(turns),
    )


# ---------------------------------------------------------------------------
# Mode B: Purchase decision simulation
# ---------------------------------------------------------------------------


@router.post(
    "/personas/{persona_id}/purchase-decision",
    response_model=PurchaseDecisionResponse,
    summary="Simulate a purchase decision",
    response_description="Stage-by-stage decision trace",
)
async def simulate_purchase_decision(
    persona_id: str,
    request: PurchaseDecisionRequest,
    store: PersonaStore = Depends(get_store),
    simulator: BehaviorSimulator = Depends(get_behavior_simulator),
) -> PurchaseDecisionResponse:
    """Simulate a consumer's purchase decision for a given product."""
    profile = store.get(persona_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Persona '{persona_id}' not found",
        )

    trace = simulator.simulate_purchase_decision(
        persona=profile,
        product={
            "name": request.product_name,
            "price_cny": request.price_cny,
            "core_selling_points": request.core_selling_points,
        },
    )

    return PurchaseDecisionResponse(
        persona_id=persona_id,
        product_name=trace.product_name,
        price_cny=trace.price_cny,
        final_decision=trace.final_decision,
        confidence=trace.confidence,
        stages=trace.stages,
        stage_count=len(trace.stages),
    )
