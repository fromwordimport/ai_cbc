"""In-memory persona storage with query support.

This is a temporary implementation for Week 1-2 development.
Production will switch to MongoDB (Beanie) or a persistent store.
"""

from __future__ import annotations

import threading

from aicbc.core.models.persona import PersonaProfile
from aicbc.questionnaire.models import CBCQuestionnaire, CBCStudy


class QuestionnaireStore:
    """Thread-safe in-memory store for CBC studies and questionnaires."""

    def __init__(self) -> None:
        self._studies: dict[str, CBCStudy] = {}
        self._questionnaires: dict[str, CBCQuestionnaire] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Study CRUD
    # ------------------------------------------------------------------

    def save_study(self, study: CBCStudy) -> None:
        """Store a study (upsert)."""
        with self._lock:
            self._studies[study.study_id] = study

    def get_study(self, study_id: str) -> CBCStudy | None:
        """Retrieve a study by ID."""
        with self._lock:
            return self._studies.get(study_id)

    def delete_study(self, study_id: str) -> bool:
        """Delete a study and its questionnaire by ID."""
        with self._lock:
            deleted = study_id in self._studies
            if deleted:
                del self._studies[study_id]
                self._questionnaires.pop(study_id, None)
            return deleted

    def list_studies(
        self,
        *,
        product_category: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[CBCStudy], int]:
        """Query studies with optional filters."""
        with self._lock:
            items = list(self._studies.values())

        if product_category is not None:
            items = [s for s in items if s.product_category == product_category]

        total = len(items)
        start = (page - 1) * page_size
        end = start + page_size
        return items[start:end], total

    # ------------------------------------------------------------------
    # Questionnaire CRUD
    # ------------------------------------------------------------------

    def save_questionnaire(self, questionnaire: CBCQuestionnaire) -> None:
        """Store a questionnaire, keyed by study_id."""
        with self._lock:
            self._questionnaires[questionnaire.study_id] = questionnaire

    def get_questionnaire(self, study_id: str) -> CBCQuestionnaire | None:
        """Retrieve the questionnaire for a study."""
        with self._lock:
            return self._questionnaires.get(study_id)

    def clear(self) -> None:
        """Clear all stored studies and questionnaires."""
        with self._lock:
            self._studies.clear()
            self._questionnaires.clear()


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


# Module-level singletons
_store: PersonaStore | None = None
_questionnaire_store: QuestionnaireStore | None = None


def get_store() -> PersonaStore:
    """Return the global PersonaStore singleton."""
    global _store
    if _store is None:
        _store = PersonaStore()
    return _store


def get_questionnaire_store() -> QuestionnaireStore:
    """Return the global QuestionnaireStore singleton."""
    global _questionnaire_store
    if _questionnaire_store is None:
        _questionnaire_store = QuestionnaireStore()
    return _questionnaire_store
