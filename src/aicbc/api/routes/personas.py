"""Persona generation API routes."""

from fastapi import APIRouter

router = APIRouter()


@router.post("/personas/batch")
async def generate_personas_batch() -> dict:
    """Generate a batch of virtual consumer personas."""
    return {"status": "not_implemented", "message": "Batch persona generation"}


@router.get("/personas/{persona_id}")
async def get_persona(persona_id: str) -> dict:
    """Get a persona by ID."""
    return {"status": "not_implemented", "persona_id": persona_id}
