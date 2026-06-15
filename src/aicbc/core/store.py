"""Pluggable persona/questionnaire/response storage.

Defaults to MongoDB in production/staging and keeps an in-memory fallback for
local development and tests.  The in-memory classes remain available as
``MemoryPersonaStore`` / ``MemoryQuestionnaireStore`` / ``MemoryResponseStore``.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from typing import Any

from aicbc.core.models.persona import PersonaProfile
from aicbc.questionnaire.models import CBCQuestionnaire, CBCStudy
from aicbc.questionnaire.response_models import CBCRawDataset, PersonaResponse

# Lazy import of MongoDB stores to avoid import-time Beanie requirement.
_MongoStores: Any | None = None


def _get_mongo_stores():
    global _MongoStores
    if _MongoStores is None:
        from aicbc.core import store_mongo

        _MongoStores = store_mongo
    return _MongoStores


def _use_memory_store() -> bool:
    """Return True if the environment requests the in-memory store."""
    env = os.environ.get("USE_MEMORY_STORE", "").lower()
    if env in ("1", "true", "yes"):
        return True
    # Default to memory in development unless MONGODB_URL is explicitly set.
    environment = os.environ.get("ENVIRONMENT", "development").lower()
    if environment in ("development", "dev", "testing", "test"):
        mongo_url = os.environ.get("MONGODB_URL", "")
        if not mongo_url or mongo_url == "mongodb://localhost:27017":
            # Even on localhost, if mongo is not reachable tests should not fail.
            return True
    return False


class MemoryQuestionnaireStore:
    """Thread-safe in-memory store for CBC studies and questionnaires."""

    def __init__(self) -> None:
        self._studies: dict[str, CBCStudy] = {}
        self._questionnaires: dict[str, CBCQuestionnaire] = {}
        self._lock = threading.Lock()

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


class MemoryResponseStore:
    """Thread-safe in-memory store for persona responses and raw datasets."""

    def __init__(self) -> None:
        self._responses: dict[str, PersonaResponse] = {}
        self._datasets: dict[str, CBCRawDataset] = {}
        self._lock = threading.Lock()

    def save_response(self, response: PersonaResponse) -> None:
        """Store a single persona response."""
        with self._lock:
            self._responses[response.response_id] = response

    def get_response(self, response_id: str) -> PersonaResponse | None:
        """Retrieve a response by ID."""
        with self._lock:
            return self._responses.get(response_id)

    def list_responses_by_study(
        self,
        study_id: str,
        page: int = 1,
        page_size: int = 100,
    ) -> tuple[list[PersonaResponse], int]:
        """Query responses for a study."""
        with self._lock:
            items = [
                r for r in self._responses.values() if r.study_id == study_id
            ]
        total = len(items)
        start = (page - 1) * page_size
        end = start + page_size
        return items[start:end], total

    def save_dataset(self, study_id: str, dataset: CBCRawDataset) -> None:
        """Store (or merge) a raw dataset for a study."""
        with self._lock:
            existing = self._datasets.get(study_id)
            if existing is not None:
                merged_records = existing.choice_records + dataset.choice_records
                existing.choice_records = merged_records
                existing.metadata.n_respondents += dataset.metadata.n_respondents
            else:
                self._datasets[study_id] = dataset

    def get_dataset(self, study_id: str) -> CBCRawDataset | None:
        """Retrieve the raw dataset for a study."""
        with self._lock:
            return self._datasets.get(study_id)

    def delete_response(self, response_id: str) -> bool:
        """Delete a single response by ID."""
        with self._lock:
            if response_id in self._responses:
                del self._responses[response_id]
                return True
            return False

    def delete_dataset(self, study_id: str) -> bool:
        """Delete the raw dataset for a study."""
        with self._lock:
            if study_id in self._datasets:
                del self._datasets[study_id]
                return True
            return False

    def delete_by_study(self, study_id: str) -> int:
        """Delete all responses and the dataset for a study."""
        with self._lock:
            response_ids = [
                rid for rid, r in self._responses.items() if r.study_id == study_id
            ]
            for rid in response_ids:
                del self._responses[rid]
            dataset_deleted = study_id in self._datasets
            if dataset_deleted:
                del self._datasets[study_id]
            return len(response_ids) + (1 if dataset_deleted else 0)

    def delete_by_persona(self, persona_id: str) -> int:
        """Delete all responses belonging to a persona."""
        with self._lock:
            response_ids = [
                rid
                for rid, r in self._responses.items()
                if r.persona_id == persona_id
            ]
            for rid in response_ids:
                del self._responses[rid]
            return len(response_ids)

    def clear(self) -> None:
        """Clear all stored responses and datasets."""
        with self._lock:
            self._responses.clear()
            self._datasets.clear()


class MemoryPersonaStore:
    """Thread-safe in-memory store for PersonaProfile objects."""

    def __init__(self) -> None:
        self._data: dict[str, PersonaProfile] = {}
        self._lock = threading.Lock()
        self._segment_index: dict[str, set[str]] = {}
        self._city_tier_index: dict[str, set[str]] = {}
        self._bias_status_index: dict[str, set[str]] = {}
        self._fingerprints: set[str] = set()

    @staticmethod
    def _compute_fingerprint(persona: PersonaProfile) -> str:
        """Compute SHA-256 fingerprint for deduplication."""
        key_data = {
            "segment": persona.segment,
            "layer1": persona.layer1_demographics.model_dump(exclude_none=True),
            "layer2": persona.layer2_behavior.model_dump(exclude_none=True),
            "layer3": persona.layer3_psychology.model_dump(exclude_none=True),
            "layer4": persona.layer4_scenarios.model_dump(exclude_none=True),
        }
        canonical = json.dumps(key_data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def is_duplicate(self, persona: PersonaProfile) -> bool:
        """Check if a persona with the same content fingerprint already exists."""
        fp = self._compute_fingerprint(persona)
        with self._lock:
            return fp in self._fingerprints

    def _add_to_index(self, persona: PersonaProfile) -> None:
        """Register a persona in all inverted indexes."""
        pid = persona.persona_id
        self._segment_index.setdefault(persona.segment, set()).add(pid)
        self._city_tier_index.setdefault(
            persona.layer1_demographics.city, set()
        ).add(pid)
        self._bias_status_index.setdefault(
            persona.bias_audit_status, set()
        ).add(pid)

    def _remove_from_index(self, persona: PersonaProfile) -> None:
        """Unregister a persona from all inverted indexes."""
        pid = persona.persona_id

        seg_set = self._segment_index.get(persona.segment)
        if seg_set is not None:
            seg_set.discard(pid)
            if not seg_set:
                del self._segment_index[persona.segment]

        city_set = self._city_tier_index.get(persona.layer1_demographics.city)
        if city_set is not None:
            city_set.discard(pid)
            if not city_set:
                del self._city_tier_index[persona.layer1_demographics.city]

        bs_set = self._bias_status_index.get(persona.bias_audit_status)
        if bs_set is not None:
            bs_set.discard(pid)
            if not bs_set:
                del self._bias_status_index[persona.bias_audit_status]

    def save(self, persona: PersonaProfile) -> bool:
        """Store a persona (upsert). Returns True if new, False if duplicate."""
        fp = self._compute_fingerprint(persona)
        with self._lock:
            if fp in self._fingerprints and persona.persona_id not in self._data:
                return False
            old = self._data.get(persona.persona_id)
            if old is not None:
                old_fp = self._compute_fingerprint(old)
                self._fingerprints.discard(old_fp)
                self._remove_from_index(old)
            self._data[persona.persona_id] = persona
            self._fingerprints.add(fp)
            self._add_to_index(persona)
            return True

    def get(self, persona_id: str) -> PersonaProfile | None:
        """Retrieve a persona by ID."""
        with self._lock:
            return self._data.get(persona_id)

    def count(self) -> int:
        """Return the total number of stored personas."""
        with self._lock:
            return len(self._data)

    def delete(self, persona_id: str) -> bool:
        """Delete a persona by ID."""
        with self._lock:
            if persona_id in self._data:
                persona = self._data[persona_id]
                self._remove_from_index(persona)
                del self._data[persona_id]
                return True
            return False

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
        """Query personas with optional filters."""
        with self._lock:
            candidate_ids: set[str] | None = None

            if segment is not None:
                seg_ids = self._segment_index.get(segment, set())
                candidate_ids = seg_ids
            if city_tier is not None:
                ct_ids = self._city_tier_index.get(city_tier, set())
                candidate_ids = (
                    ct_ids
                    if candidate_ids is None
                    else candidate_ids & ct_ids
                )
            if bias_status is not None:
                bs_ids = self._bias_status_index.get(bias_status, set())
                candidate_ids = (
                    bs_ids
                    if candidate_ids is None
                    else candidate_ids & bs_ids
                )

            if candidate_ids is not None:
                items = [self._data[pid] for pid in candidate_ids if pid in self._data]
            else:
                items = list(self._data.values())

        if study_id is not None:
            prefix = f"persona-{study_id}-"
            items = [p for p in items if p.persona_id.startswith(prefix)]
        if segment is not None:
            items = [p for p in items if p.segment == segment]
        if city_tier is not None:
            items = [p for p in items if p.layer1_demographics.city == city_tier]
        if bias_status is not None:
            items = [p for p in items if p.bias_audit_status == bias_status]

        total = len(items)
        start = (page - 1) * page_size
        end = start + page_size
        return items[start:end], total

    def delete_by_study(self, study_id: str) -> int:
        """Delete all personas belonging to a study and return count."""
        prefix = f"persona-{study_id}-"
        with self._lock:
            ids = [pid for pid in self._data if pid.startswith(prefix)]
            for pid in ids:
                persona = self._data[pid]
                self._remove_from_index(persona)
                del self._data[pid]
            # Recompute fingerprints for remaining personas.
            self._fingerprints = {
                self._compute_fingerprint(p) for p in self._data.values()
            }
            return len(ids)

    def clear(self) -> None:
        """Clear all stored personas and reset indexes."""
        with self._lock:
            self._data.clear()
            self._segment_index.clear()
            self._city_tier_index.clear()
            self._bias_status_index.clear()
            self._fingerprints.clear()


# Aliases for backward compatibility.
QuestionnaireStore = MemoryQuestionnaireStore
ResponseStore = MemoryResponseStore
PersonaStore = MemoryPersonaStore


# Module-level singletons
_store: PersonaStore | None = None
_questionnaire_store: QuestionnaireStore | None = None
_response_store: ResponseStore | None = None


def _create_persona_store() -> PersonaStore:
    if _use_memory_store():
        return MemoryPersonaStore()
    mongo = _get_mongo_stores()
    return mongo.MongoPersonaStore()


def _create_questionnaire_store() -> QuestionnaireStore:
    if _use_memory_store():
        return MemoryQuestionnaireStore()
    mongo = _get_mongo_stores()
    return mongo.MongoQuestionnaireStore()


def _create_response_store() -> ResponseStore:
    if _use_memory_store():
        return MemoryResponseStore()
    mongo = _get_mongo_stores()
    return mongo.MongoResponseStore()


def get_store() -> PersonaStore:
    """Return the global PersonaStore singleton."""
    global _store
    if _store is None:
        _store = _create_persona_store()
    return _store


def get_questionnaire_store() -> QuestionnaireStore:
    """Return the global QuestionnaireStore singleton."""
    global _questionnaire_store
    if _questionnaire_store is None:
        _questionnaire_store = _create_questionnaire_store()
    return _questionnaire_store


def get_response_store() -> ResponseStore:
    """Return the global ResponseStore singleton."""
    global _response_store
    if _response_store is None:
        _response_store = _create_response_store()
    return _response_store


def reset_stores() -> None:
    """Reset all global store singletons to clean state."""
    global _store, _questionnaire_store, _response_store
    _store = None
    _questionnaire_store = None
    _response_store = None
    # Also clear the underlying memory stores if they are currently active.
    get_store().clear()
    get_questionnaire_store().clear()
    get_response_store().clear()
    # Then reset again so next callers get fresh instances.
    _store = None
    _questionnaire_store = None
    _response_store = None
