"""Simulation API routes."""

from fastapi import APIRouter

router = APIRouter()


@router.post("/simulations")
async def run_simulation() -> dict:
    """Run a single simulation."""
    return {"status": "not_implemented", "message": "Single simulation"}


@router.post("/simulations/batch")
async def run_simulation_batch() -> dict:
    """Run a batch of simulations."""
    return {"status": "not_implemented", "message": "Batch simulation"}
