"""In-memory persona storage with query support.

This is a temporary implementation for Week 1-2 development.
Production will switch to MongoDB (Beanie) or a persistent store.
"""

from __future__ import annotations

import threading
from typing import Any

from aicbc.core.models.persona import PersonaProfile


class PersonaStore:
    """Thread-safe in-memory store for PersonaProfile objects."""

    def __init__(self) -> None:
        self._data: dict[str, PersonaProfile] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def save(self, persona: PersonaProfile) -> None:
        """Store a persona (upsert)."""
        with self._lock:
            self._data[persona.persona_id] = persona

    def get(self, persona_id: str) -> PersonaProfile | None:
        """Retrieve a persona by ID."""
        with self._lock:
            return self._data.get(persona_id)

    def delete(self, persona_id: str) -> bool:
        """Delete a persona by ID. Returns True if deleted."""
        with self._lock:
            if persona_id in self._data:
                del self._data[persona_id]
                return True
            return False

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_all(
        self,
        *,
        study_id: str | None = None,
        segment: str | None = None,
        city_tier: str | None = None,
        bias_status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[PersonaProfile], int]:
        """Query personas with optional filters.

        Returns:
            Tuple of (page_items, total_count).
        """
        with self._lock:
            items = list(self._data.values())

        if study_id is not None:
            items = [p for p in items if p.persona_id.startswith(f"persona-{study_id}-")]
        if segment is not None:
            items = [p for p in items if segment in p.segment]
        if city_tier is not None:
            items = [p for p in items if city_tier in p.layer1_demographics.city]
        if bias_status is not None:
            items = [p for p in items if p.bias_audit_status == bias_status]

        total = len(items)
        start = (page - 1) * page_size
        end = start + page_size
        return items[start:end], total

    def count(self) -> int:
        """Total number of stored personas."""
        with self._lock:
            return len(self._data)

    def clear(self) -> None:
        """Clear all stored personas (useful for testing)."""
        with self._lock:
            self._data.clear()


# Module-level singleton
_store: PersonaStore | None = None


def get_store() -> PersonaStore:
    """Return the global PersonaStore singleton."""
    global _store
    if _store is None:
        _store = PersonaStore()
    return _store
