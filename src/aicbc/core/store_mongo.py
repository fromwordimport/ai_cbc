"""MongoDB-backed implementations of the AI_CBC stores.

These classes mirror the public API of the in-memory stores in
``aicbc.core.store`` and ``aicbc.analysis.store`` but persist data to MongoDB
using Beanie.  Each method is synchronous on the outside so existing sync
route handlers can keep calling them unchanged; internally they run the
Beanie coroutine in a fresh event loop via ``asyncio.run`` (safe because
FastAPI executes sync handlers in a thread-pool thread).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from typing import Any, TypeVar

from aicbc.analysis.models import (
    AnalysisJobStatus,
    AnalysisResultResponse,
    ConvergenceDiagnostics,
    ImportanceResponse,
    MarketSimResponse,
    SegmentComparisonResponse,
    WTPResponse,
)
from aicbc.core.models.db_documents import (
    AnalysisDerivativeDocument,
    AnalysisJobDocument,
    AnalysisResultDocument,
    DatasetDocument,
    PersonaDocument,
    QuestionnaireDocument,
    ResponseDocument,
    StudyDocument,
)
from aicbc.core.models.persona import PersonaProfile
from aicbc.questionnaire.models import CBCQuestionnaire, CBCStudy
from aicbc.questionnaire.response_models import CBCRawDataset, PersonaResponse

T = TypeVar("T")

_worker_loop: asyncio.AbstractEventLoop | None = None


def set_worker_loop(loop: asyncio.AbstractEventLoop | None) -> None:
    """Set the persistent event loop used by Celery worker processes.

    Motor/Beanie require a single long-lived event loop.  In a Celery prefork
    worker, ``asyncio.run`` would create and close a new loop per operation,
    leaving Motor bound to a closed loop.  The worker initializer sets this
    once per process; the API process leaves it unset and continues to use
    ``asyncio.run``.
    """
    global _worker_loop
    _worker_loop = loop


def _run_coro(coro: asyncio.Coroutine[Any, Any, T]) -> T:
    """Run a coroutine on the worker loop if available, else ``asyncio.run``."""
    if _worker_loop is not None and not _worker_loop.is_closed():
        return _worker_loop.run_until_complete(coro)
    return asyncio.run(coro)


# Backward-compatible alias used by older tests that patch _run.
_run = _run_coro


class MongoPersonaStore:
    """MongoDB-backed persona store."""

    @staticmethod
    def _compute_fingerprint(persona: PersonaProfile) -> str:
        """Compute SHA-256 fingerprint from persona four-layer content."""
        key_data = {
            "segment": persona.segment,
            "layer1": persona.layer1_demographics.model_dump(exclude_none=True),
            "layer2": persona.layer2_behavior.model_dump(exclude_none=True),
            "layer3": persona.layer3_psychology.model_dump(exclude_none=True),
            "layer4": persona.layer4_scenarios.model_dump(exclude_none=True),
        }
        canonical = json.dumps(key_data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _doc_from_persona(self, persona: PersonaProfile) -> PersonaDocument:
        """Convert a PersonaProfile to a PersonaDocument."""
        return PersonaDocument(
            persona_id=persona.persona_id,
            fingerprint=self._compute_fingerprint(persona),
            segment=persona.segment,
            city=persona.layer1_demographics.city,
            bias_audit_status=persona.bias_audit_status,
            status=persona.status,
            data=persona.model_dump(mode="json"),
        )

    def _persona_from_doc(self, doc: PersonaDocument) -> PersonaProfile:
        """Convert a PersonaDocument back to a PersonaProfile."""
        return PersonaProfile.model_validate(doc.data)

    def is_duplicate(self, persona: PersonaProfile) -> bool:
        """Check whether a persona with the same content fingerprint exists."""
        return _run_coro(self.ais_duplicate(persona))

    async def ais_duplicate(self, persona: PersonaProfile) -> bool:
        """Async version of :meth:`is_duplicate`."""
        fp = self._compute_fingerprint(persona)
        existing = await PersonaDocument.find_one(PersonaDocument.fingerprint == fp)
        return existing is not None

    def save(self, persona: PersonaProfile) -> bool:
        """Persist a persona (upsert). Returns True if stored, False if duplicate."""
        return _run_coro(self.asave(persona))

    async def asave(self, persona: PersonaProfile) -> bool:
        """Async version of :meth:`save`."""
        fp = self._compute_fingerprint(persona)
        existing = await PersonaDocument.find_one(PersonaDocument.persona_id == persona.persona_id)
        if existing is not None:
            doc = self._doc_from_persona(persona)
            doc.id = existing.id
            await doc.save()
            return True

        # Duplicate content guard for new personas.
        duplicate = await PersonaDocument.find_one(PersonaDocument.fingerprint == fp)
        if duplicate is not None:
            return False

        doc = self._doc_from_persona(persona)
        await doc.insert()
        return True

    def get(self, persona_id: str) -> PersonaProfile | None:
        """Retrieve a persona by ID."""
        return _run_coro(self.aget(persona_id))

    async def aget(self, persona_id: str) -> PersonaProfile | None:
        """Async version of :meth:`get`."""
        doc = await PersonaDocument.find_one(PersonaDocument.persona_id == persona_id)
        if doc is None:
            return None
        return self._persona_from_doc(doc)

    def delete(self, persona_id: str) -> bool:
        """Delete a persona by ID."""
        return _run_coro(self.adelete(persona_id))

    async def adelete(self, persona_id: str) -> bool:
        """Async version of :meth:`delete`."""
        doc = await PersonaDocument.find_one(PersonaDocument.persona_id == persona_id)
        if doc is None:
            return False
        await doc.delete()
        return True

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
        """Query personas with optional filters and pagination."""
        return _run_coro(
            self.alist_all(
                study_id=study_id,
                segment=segment,
                city_tier=city_tier,
                bias_status=bias_status,
                page=page,
                page_size=page_size,
            )
        )

    async def alist_all(
        self,
        *,
        study_id: str | None = None,
        segment: str | None = None,
        city_tier: str | None = None,
        bias_status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[PersonaProfile], int]:
        """Async version of :meth:`list_all`.

        Pushes filtering and pagination down to MongoDB so large persona
        collections do not block the event loop or exhaust memory.
        """
        query: Any = {}
        if segment is not None:
            query["segment"] = segment
        if city_tier is not None:
            query["city"] = city_tier
        if bias_status is not None:
            query["bias_audit_status"] = bias_status
        if study_id is not None:
            prefix = f"persona-{study_id}-"
            query["persona_id"] = {"$regex": f"^{prefix}"}

        mongo_query = PersonaDocument.find(query)
        total = await mongo_query.count()
        start = (page - 1) * page_size
        docs = await mongo_query.skip(start).limit(page_size).to_list()
        items = [self._persona_from_doc(d) for d in docs]
        return items, total

    def delete_by_study(self, study_id: str) -> int:
        """Delete all personas belonging to a study."""
        return _run_coro(self.adelete_by_study(study_id))

    async def adelete_by_study(self, study_id: str) -> int:
        """Async version of :meth:`delete_by_study`."""
        prefix = f"persona-{study_id}-"
        docs = await PersonaDocument.find({"persona_id": {"$regex": f"^{prefix}"}}).to_list()
        for doc in docs:
            await doc.delete()
        return len(docs)

    def count(self) -> int:
        """Total number of stored personas."""
        return _run_coro(self.acount())

    async def acount(self) -> int:
        """Async total number of stored personas."""
        return await PersonaDocument.count()

    async def aclear(self) -> None:
        """Delete all personas (async)."""
        await PersonaDocument.delete_all()


class MongoQuestionnaireStore:
    """MongoDB-backed study and questionnaire store."""

    def save_study(self, study: CBCStudy) -> None:
        """Persist a study (upsert)."""
        _run_coro(self.asave_study(study))

    async def asave_study(self, study: CBCStudy) -> None:
        """Async version of :meth:`save_study`."""
        doc = await StudyDocument.find_one(StudyDocument.study_id == study.study_id)
        data = study.model_dump(mode="json")
        if doc is not None:
            doc.data = data
            doc.status = study.status.value
            await doc.save()
        else:
            await StudyDocument(
                study_id=study.study_id,
                product_category=study.product_category,
                status=study.status.value,
                data=data,
            ).insert()

    def get_study(self, study_id: str) -> CBCStudy | None:
        """Retrieve a study by ID."""
        return _run_coro(self.aget_study(study_id))

    async def aget_study(self, study_id: str) -> CBCStudy | None:
        """Async version of :meth:`get_study`."""
        doc = await StudyDocument.find_one(StudyDocument.study_id == study_id)
        if doc is None:
            return None
        return CBCStudy.model_validate(doc.data)

    def delete_study(self, study_id: str) -> bool:
        """Delete a study and its questionnaire."""
        return _run_coro(self.adelete_study(study_id))

    async def adelete_study(self, study_id: str) -> bool:
        """Async version of :meth:`delete_study`."""
        study_doc = await StudyDocument.find_one(StudyDocument.study_id == study_id)
        if study_doc is None:
            return False
        await study_doc.delete()
        questionnaire = await QuestionnaireDocument.find_one(
            QuestionnaireDocument.study_id == study_id
        )
        if questionnaire is not None:
            await questionnaire.delete()
        return True

    def list_studies(
        self,
        *,
        product_category: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[CBCStudy], int]:
        """Query studies with optional filters."""
        return _run_coro(
            self.alist_studies(product_category=product_category, page=page, page_size=page_size)
        )

    async def acount_studies_by_status(self) -> dict[str, int]:
        """Return study counts grouped by status using MongoDB aggregation."""
        pipeline: list[dict[str, Any]] = [
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ]
        cursor = StudyDocument.get_motor_collection().aggregate(pipeline)
        results = await cursor.to_list(length=None)
        return {str(r["_id"]): r["count"] for r in results}

    async def alist_recent_studies(
        self,
        since: datetime,
        limit: int = 10,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return lightweight recent study summaries and total count.

        Uses projection to avoid transferring the full ``data`` field.
        """
        query: Any = {"created_at": {"$gte": since}}
        projection = {
            "study_id": 1,
            "product_category": 1,
            "status": 1,
            "created_at": 1,
            "_id": 0,
        }
        total = await StudyDocument.find(query).count()
        cursor = StudyDocument.get_motor_collection().find(
            query, projection=projection
        ).sort("created_at", -1).limit(limit)
        docs = await cursor.to_list(length=None)
        return docs, total

    def count_studies_by_status(self) -> dict[str, int]:
        """Synchronous version of :meth:`acount_studies_by_status`."""
        return _run_coro(self.acount_studies_by_status())

    def list_recent_studies(
        self,
        since: datetime,
        limit: int = 10,
    ) -> tuple[list[dict[str, Any]], int]:
        """Synchronous version of :meth:`alist_recent_studies`."""
        return _run_coro(self.alist_recent_studies(since, limit))

    def save_questionnaire(self, questionnaire: CBCQuestionnaire) -> None:
        """Persist a questionnaire keyed by study_id."""
        _run_coro(self.asave_questionnaire(questionnaire))

    async def asave_questionnaire(self, questionnaire: CBCQuestionnaire) -> None:
        """Async version of :meth:`save_questionnaire`."""
        doc = await QuestionnaireDocument.find_one(
            QuestionnaireDocument.study_id == questionnaire.study_id
        )
        data = questionnaire.model_dump(mode="json")
        if doc is not None:
            doc.data = data
            doc.questionnaire_id = questionnaire.questionnaire_id
            await doc.save()
        else:
            await QuestionnaireDocument(
                questionnaire_id=questionnaire.questionnaire_id,
                study_id=questionnaire.study_id,
                data=data,
            ).insert()

    def get_questionnaire(self, study_id: str) -> CBCQuestionnaire | None:
        """Retrieve the questionnaire for a study."""
        return _run_coro(self.aget_questionnaire(study_id))

    async def aget_questionnaire(self, study_id: str) -> CBCQuestionnaire | None:
        """Async version of :meth:`get_questionnaire`."""
        doc = await QuestionnaireDocument.find_one(QuestionnaireDocument.study_id == study_id)
        if doc is None:
            return None
        return CBCQuestionnaire.model_validate(doc.data)

    async def aclear(self) -> None:
        """Delete all studies and questionnaires (async)."""
        await StudyDocument.delete_all()
        await QuestionnaireDocument.delete_all()


class MongoResponseStore:
    """MongoDB-backed response and dataset store."""

    def save_response(self, response: PersonaResponse) -> None:
        """Persist a single persona response."""
        _run_coro(self.asave_response(response))

    async def asave_response(self, response: PersonaResponse) -> None:
        """Async version of :meth:`save_response`."""
        doc = await ResponseDocument.find_one(ResponseDocument.response_id == response.response_id)
        data = response.model_dump(mode="json")
        if doc is not None:
            doc.data = data
            doc.study_id = response.study_id
            doc.persona_id = response.persona_id
            await doc.save()
        else:
            await ResponseDocument(
                response_id=response.response_id,
                study_id=response.study_id,
                persona_id=response.persona_id,
                data=data,
            ).insert()

    def get_response(self, response_id: str) -> PersonaResponse | None:
        """Retrieve a response by ID."""
        return _run_coro(self.aget_response(response_id))

    async def aget_response(self, response_id: str) -> PersonaResponse | None:
        """Async version of :meth:`get_response`."""
        doc = await ResponseDocument.find_one(ResponseDocument.response_id == response_id)
        if doc is None:
            return None
        return PersonaResponse.model_validate(doc.data)

    def list_responses_by_study(
        self,
        study_id: str,
        page: int = 1,
        page_size: int = 100,
    ) -> tuple[list[PersonaResponse], int]:
        """Query responses for a study."""
        return _run_coro(self.alist_responses_by_study(study_id, page=page, page_size=page_size))

    async def alist_responses_by_study(
        self,
        study_id: str,
        page: int = 1,
        page_size: int = 100,
    ) -> tuple[list[PersonaResponse], int]:
        """Async version of :meth:`list_responses_by_study`."""
        mongo_query = ResponseDocument.find(ResponseDocument.study_id == study_id)
        total = await mongo_query.count()
        start = (page - 1) * page_size
        docs = await mongo_query.skip(start).limit(page_size).to_list()
        items = [PersonaResponse.model_validate(d.data) for d in docs]
        return items, total

    def save_dataset(self, study_id: str, dataset: CBCRawDataset) -> None:
        """Persist a raw dataset for a study, replacing any existing dataset."""
        _run_coro(self.asave_dataset(study_id, dataset))

    async def asave_dataset(self, study_id: str, dataset: CBCRawDataset) -> None:
        """Async version of :meth:`save_dataset`."""
        doc = await DatasetDocument.find_one(DatasetDocument.study_id == study_id)
        data = dataset.model_dump(mode="json")
        if doc is not None:
            doc.data = data
            doc.updated_at = datetime.now(UTC)
            await doc.save()
        else:
            await DatasetDocument(
                study_id=study_id,
                data=data,
            ).insert()

    def get_dataset(self, study_id: str) -> CBCRawDataset | None:
        """Retrieve the raw dataset for a study."""
        return _run_coro(self.aget_dataset(study_id))

    async def aget_dataset(self, study_id: str) -> CBCRawDataset | None:
        """Async version of :meth:`get_dataset`."""
        doc = await DatasetDocument.find_one(DatasetDocument.study_id == study_id)
        if doc is None:
            return None
        return CBCRawDataset.model_validate(doc.data)

    def delete_response(self, response_id: str) -> bool:
        """Delete a single response by ID."""
        return _run_coro(self.adelete_response(response_id))

    async def adelete_response(self, response_id: str) -> bool:
        """Async version of :meth:`delete_response`."""
        doc = await ResponseDocument.find_one(ResponseDocument.response_id == response_id)
        if doc is None:
            return False
        await doc.delete()
        return True

    def delete_dataset(self, study_id: str) -> bool:
        """Delete the raw dataset for a study."""
        return _run_coro(self.adelete_dataset(study_id))

    async def adelete_dataset(self, study_id: str) -> bool:
        """Async version of :meth:`delete_dataset`."""
        doc = await DatasetDocument.find_one(DatasetDocument.study_id == study_id)
        if doc is None:
            return False
        await doc.delete()
        return True

    def delete_by_study(self, study_id: str) -> int:
        """Delete all responses and the dataset for a study."""
        return _run_coro(self.adelete_by_study(study_id))

    async def adelete_by_study(self, study_id: str) -> int:
        """Async version of :meth:`delete_by_study`."""
        response_docs = await ResponseDocument.find(ResponseDocument.study_id == study_id).to_list()
        for doc in response_docs:
            await doc.delete()
        dataset_deleted = await self.adelete_dataset(study_id)
        return len(response_docs) + (1 if dataset_deleted else 0)

    def delete_by_persona(self, persona_id: str) -> int:
        """Delete all responses belonging to a persona."""
        return _run_coro(self.adelete_by_persona(persona_id))

    async def adelete_by_persona(self, persona_id: str) -> int:
        """Async version of :meth:`delete_by_persona`."""
        docs = await ResponseDocument.find(ResponseDocument.persona_id == persona_id).to_list()
        for doc in docs:
            await doc.delete()
        return len(docs)

    async def aclear(self) -> None:
        """Delete all responses and datasets (async)."""
        await ResponseDocument.delete_all()
        await DatasetDocument.delete_all()


class MongoAnalysisStore:
    """MongoDB-backed analysis job and result store."""

    _VALID_TRANSITIONS: dict[str, set[str]] = {
        "PENDING": {"QUEUED", "RUNNING", "CANCELLED"},
        "QUEUED": {"RUNNING", "CANCELLED"},
        "RUNNING": {"COMPLETED", "FAILED", "TIMED_OUT", "CANCELLED"},
        "COMPLETED": set(),
        "FAILED": set(),
        "CANCELLED": set(),
        "TIMED_OUT": set(),
    }

    def save_job(self, job: AnalysisJobStatus) -> None:
        """Persist a job status (upsert)."""
        _run_coro(self.asave_job(job))

    async def asave_job(self, job: AnalysisJobStatus) -> None:
        """Async version of :meth:`save_job`."""
        doc = await AnalysisJobDocument.find_one(AnalysisJobDocument.analysis_id == job.analysis_id)
        data = job.model_dump(mode="json")
        if doc is not None:
            doc.data = data
            doc.status = job.status
            await doc.save()
        else:
            await AnalysisJobDocument(
                analysis_id=job.analysis_id,
                study_id=job.study_id,
                status=job.status,
                data=data,
            ).insert()

    def get_job(self, analysis_id: str) -> AnalysisJobStatus | None:
        """Retrieve a job by ID."""
        return _run_coro(self.aget_job(analysis_id))

    async def aget_job(self, analysis_id: str) -> AnalysisJobStatus | None:
        """Async version of :meth:`get_job`."""
        doc = await AnalysisJobDocument.find_one(AnalysisJobDocument.analysis_id == analysis_id)
        if doc is None:
            return None
        return AnalysisJobStatus.model_validate(doc.data)

    def update_job_status(
        self,
        analysis_id: str,
        status: str,
        progress: float | None = None,
    ) -> AnalysisJobStatus | None:
        """Update job status enforcing legal transitions."""
        return _run_coro(self.aupdate_job_status(analysis_id, status, progress))

    async def aupdate_job_status(
        self,
        analysis_id: str,
        status: str,
        progress: float | None = None,
    ) -> AnalysisJobStatus | None:
        """Async version of :meth:`update_job_status`."""
        doc = await AnalysisJobDocument.find_one(AnalysisJobDocument.analysis_id == analysis_id)
        if doc is None:
            return None

        job = AnalysisJobStatus.model_validate(doc.data)
        allowed = self._VALID_TRANSITIONS.get(job.status, set())
        if allowed and status not in allowed:
            import structlog

            log = structlog.get_logger("aicbc.analysis")
            log.warning(
                "illegal_state_transition",
                analysis_id=analysis_id,
                current=job.status,
                attempted=status,
            )
            return job

        job.status = status
        if status == "RUNNING" and job.started_at is None:
            job.started_at = datetime.now(UTC)
        if status in ("COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT") and job.completed_at is None:
            job.completed_at = datetime.now(UTC)
        if progress is not None:
            job.progress_percent = progress

        doc.data = job.model_dump(mode="json")
        doc.status = job.status
        await doc.save()
        return job

    def save_result(self, result: AnalysisResultResponse) -> None:
        """Persist a complete analysis result."""
        _run_coro(self.asave_result(result))

    async def asave_result(self, result: AnalysisResultResponse) -> None:
        """Async version of :meth:`save_result`."""
        doc = await AnalysisResultDocument.find_one(
            AnalysisResultDocument.analysis_id == result.analysis_id
        )
        data = result.model_dump(mode="json")
        if doc is not None:
            doc.data = data
            await doc.save()
        else:
            await AnalysisResultDocument(
                analysis_id=result.analysis_id,
                study_id=result.study_id,
                data=data,
            ).insert()

    def get_result(self, analysis_id: str) -> AnalysisResultResponse | None:
        """Retrieve a complete analysis result."""
        return _run_coro(self.aget_result(analysis_id))

    async def aget_result(self, analysis_id: str) -> AnalysisResultResponse | None:
        """Async version of :meth:`get_result`."""
        doc = await AnalysisResultDocument.find_one(
            AnalysisResultDocument.analysis_id == analysis_id
        )
        if doc is None:
            return None
        return AnalysisResultResponse.model_validate(doc.data)

    def save_convergence(self, analysis_id: str, diag: ConvergenceDiagnostics) -> None:
        """Persist convergence diagnostics."""
        _run_coro(self.asave_convergence(analysis_id, diag))

    async def asave_convergence(self, analysis_id: str, diag: ConvergenceDiagnostics) -> None:
        """Async version of :meth:`save_convergence`."""
        await self._save_derivative(analysis_id, "convergence", None, diag.model_dump(mode="json"))

    def get_convergence(self, analysis_id: str) -> ConvergenceDiagnostics | None:
        """Retrieve convergence diagnostics."""
        return _run_coro(self.aget_convergence(analysis_id))

    async def aget_convergence(self, analysis_id: str) -> ConvergenceDiagnostics | None:
        """Async version of :meth:`get_convergence`."""
        doc = await self._get_derivative(analysis_id, "convergence", None)
        if doc is None:
            return None
        return ConvergenceDiagnostics.model_validate(doc.data)

    def save_importance(self, analysis_id: str, importance: ImportanceResponse) -> None:
        """Persist attribute importance results."""
        _run_coro(self.asave_importance(analysis_id, importance))

    async def asave_importance(self, analysis_id: str, importance: ImportanceResponse) -> None:
        """Async version of :meth:`save_importance`."""
        await self._save_derivative(
            analysis_id, "importance", None, importance.model_dump(mode="json")
        )

    def get_importance(self, analysis_id: str) -> ImportanceResponse | None:
        """Retrieve attribute importance results."""
        return _run_coro(self.aget_importance(analysis_id))

    async def aget_importance(self, analysis_id: str) -> ImportanceResponse | None:
        """Async version of :meth:`get_importance`."""
        doc = await self._get_derivative(analysis_id, "importance", None)
        if doc is None:
            return None
        return ImportanceResponse.model_validate(doc.data)

    def save_wtp(self, analysis_id: str, wtp: WTPResponse) -> None:
        """Persist WTP results."""
        _run_coro(self.asave_wtp(analysis_id, wtp))

    async def asave_wtp(self, analysis_id: str, wtp: WTPResponse) -> None:
        """Async version of :meth:`save_wtp`."""
        await self._save_derivative(analysis_id, "wtp", None, wtp.model_dump(mode="json"))

    def get_wtp(self, analysis_id: str) -> WTPResponse | None:
        """Retrieve WTP results."""
        return _run_coro(self.aget_wtp(analysis_id))

    async def aget_wtp(self, analysis_id: str) -> WTPResponse | None:
        """Async version of :meth:`get_wtp`."""
        doc = await self._get_derivative(analysis_id, "wtp", None)
        if doc is None:
            return None
        return WTPResponse.model_validate(doc.data)

    def save_market_sim(self, analysis_id: str, sim_id: str, result: MarketSimResponse) -> None:
        """Persist market simulation result keyed by analysis_id + sim_id."""
        _run_coro(self.asave_market_sim(analysis_id, sim_id, result))

    async def asave_market_sim(
        self, analysis_id: str, sim_id: str, result: MarketSimResponse
    ) -> None:
        """Async version of :meth:`save_market_sim`."""
        await self._save_derivative(
            analysis_id,
            "market_sim",
            sim_id,
            result.model_dump(mode="json"),
        )

    def get_market_sim(self, analysis_id: str, sim_id: str) -> MarketSimResponse | None:
        """Retrieve market simulation result."""
        return _run_coro(self.aget_market_sim(analysis_id, sim_id))

    async def aget_market_sim(self, analysis_id: str, sim_id: str) -> MarketSimResponse | None:
        """Async version of :meth:`get_market_sim`."""
        doc = await self._get_derivative(analysis_id, "market_sim", sim_id)
        if doc is None:
            return None
        return MarketSimResponse.model_validate(doc.data)

    def get_latest_market_sim(self, analysis_id: str) -> MarketSimResponse | None:
        """Return the most recent market simulation for an analysis."""
        return _run_coro(self.aget_latest_market_sim(analysis_id))

    async def aget_latest_market_sim(self, analysis_id: str) -> MarketSimResponse | None:
        """Async version of :meth:`get_latest_market_sim`."""
        docs = (
            await AnalysisDerivativeDocument.find(
                {
                    "analysis_id": analysis_id,
                    "kind": "market_sim",
                }
            )
            .sort("created_at", -1)
            .to_list()
        )
        if not docs:
            return None
        return MarketSimResponse.model_validate(docs[0].data)

    def save_latent_class_result(self, analysis_id: str, result: dict[str, Any]) -> None:
        """Store a latent class model result."""
        _run_coro(self.asave_latent_class_result(analysis_id, result))

    async def asave_latent_class_result(self, analysis_id: str, result: dict[str, Any]) -> None:
        """Async version of :meth:`save_latent_class_result`."""
        await self._save_derivative(
            analysis_id,
            "latent_class",
            None,
            result,
        )

    def get_latent_class_result(self, analysis_id: str) -> dict[str, Any] | None:
        """Retrieve a latent class model result."""
        return _run_coro(self.aget_latent_class_result(analysis_id))

    async def aget_latent_class_result(self, analysis_id: str) -> dict[str, Any] | None:
        """Async version of :meth:`get_latent_class_result`."""
        doc = await self._get_derivative(analysis_id, "latent_class", None)
        if doc is None:
            return None
        return doc.data

    def save_segment_comparison(
        self,
        analysis_id: str,
        segment_a: str,
        segment_b: str,
        result: SegmentComparisonResponse,
    ) -> None:
        """Persist segment comparison result."""
        _run_coro(self.asave_segment_comparison(analysis_id, segment_a, segment_b, result))

    async def asave_segment_comparison(
        self,
        analysis_id: str,
        segment_a: str,
        segment_b: str,
        result: SegmentComparisonResponse,
    ) -> None:
        """Async version of :meth:`save_segment_comparison`."""
        key = f"{segment_a}:{segment_b}"
        await self._save_derivative(
            analysis_id,
            "segment_comparison",
            key,
            result.model_dump(mode="json"),
        )

    def get_segment_comparison(
        self,
        analysis_id: str,
        segment_a: str | None = None,
        segment_b: str | None = None,
    ) -> SegmentComparisonResponse | None:
        """Retrieve segment comparison result."""
        return _run_coro(self.aget_segment_comparison(analysis_id, segment_a, segment_b))

    async def aget_segment_comparison(
        self,
        analysis_id: str,
        segment_a: str | None = None,
        segment_b: str | None = None,
    ) -> SegmentComparisonResponse | None:
        """Async version of :meth:`get_segment_comparison`."""
        if segment_a is not None and segment_b is not None:
            key = f"{segment_a}:{segment_b}"
            doc = await self._get_derivative(analysis_id, "segment_comparison", key)
            if doc is None:
                return None
            return SegmentComparisonResponse.model_validate(doc.data)

        # Backward-compatible prefix scan.
        docs = (
            await AnalysisDerivativeDocument.find(
                {
                    "analysis_id": analysis_id,
                    "kind": "segment_comparison",
                }
            )
            .sort("created_at", -1)
            .to_list()
        )
        if not docs:
            return None
        return SegmentComparisonResponse.model_validate(docs[0].data)

    def list_jobs_by_study(self, study_id: str) -> list[AnalysisJobStatus]:
        """Return all analysis jobs belonging to a study."""
        return _run_coro(self.alist_jobs_by_study(study_id))

    async def alist_jobs_by_study(self, study_id: str) -> list[AnalysisJobStatus]:
        """Async version of :meth:`list_jobs_by_study`."""
        docs = await AnalysisJobDocument.find(AnalysisJobDocument.study_id == study_id).to_list()
        return [AnalysisJobStatus.model_validate(doc.data) for doc in docs]

    def delete_analysis(self, analysis_id: str) -> bool:
        """Delete a job, its result, and all derivative artefacts."""
        return _run_coro(self.adelete_analysis(analysis_id))

    async def adelete_analysis(self, analysis_id: str) -> bool:
        """Async version of :meth:`delete_analysis`."""
        job_doc = await AnalysisJobDocument.find_one(AnalysisJobDocument.analysis_id == analysis_id)
        if job_doc is None:
            return False

        await job_doc.delete()

        result_doc = await AnalysisResultDocument.find_one(
            AnalysisResultDocument.analysis_id == analysis_id
        )
        if result_doc is not None:
            await result_doc.delete()

        derivative_docs = await AnalysisDerivativeDocument.find(
            AnalysisDerivativeDocument.analysis_id == analysis_id
        ).to_list()
        for doc in derivative_docs:
            await doc.delete()
        return True

    async def _save_derivative(
        self,
        analysis_id: str,
        kind: str,
        key: str | None,
        data: dict[str, Any],
    ) -> None:
        """Upsert a derivative artefact for an analysis."""
        query: dict[str, Any] = {"analysis_id": analysis_id, "kind": kind}
        if key is not None:
            query["key"] = key
        doc = await AnalysisDerivativeDocument.find_one(query)
        if doc is not None:
            doc.data = data
            await doc.save()
        else:
            await AnalysisDerivativeDocument(
                analysis_id=analysis_id,
                study_id="",
                kind=kind,
                key=key,
                data=data,
            ).insert()

    async def _get_derivative(
        self,
        analysis_id: str,
        kind: str,
        key: str | None,
    ) -> AnalysisDerivativeDocument | None:
        """Fetch a derivative artefact for an analysis."""
        query: dict[str, Any] = {"analysis_id": analysis_id, "kind": kind}
        if key is not None:
            query["key"] = key
        return await AnalysisDerivativeDocument.find_one(query)

    def delete_by_study(self, study_id: str) -> int:
        """Delete all analyses belonging to a study."""
        return _run_coro(self.adelete_by_study(study_id))

    async def adelete_by_study(self, study_id: str) -> int:
        """Async version of :meth:`delete_by_study`."""
        docs = await AnalysisJobDocument.find(AnalysisJobDocument.study_id == study_id).to_list()
        for doc in docs:
            await self.adelete_analysis(doc.analysis_id)
        return len(docs)

    async def aclear(self) -> None:
        """Delete all analysis data (async)."""
        await AnalysisJobDocument.delete_all()
        await AnalysisResultDocument.delete_all()
        await AnalysisDerivativeDocument.delete_all()
