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
from typing import Any

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


def _run(awaitable: Any) -> Any:
    """Run an awaitable Beanie query, creating a fresh event loop if necessary.

    FastAPI executes sync route handlers in a thread-pool thread that has no
    running loop, so ``asyncio.run`` works.  In test runners that already have
    an active loop we fall back to running the awaitable in a dedicated thread
    with its own loop.  Beanie query objects are awaitable but not coroutines,
    so we wrap them in a coroutine before passing to ``asyncio.run``.
    """

    async def _execute() -> Any:
        return await awaitable

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_execute())

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(asyncio.run, _execute())
        return future.result()


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

    def _doc_from_persona(
        self, persona: PersonaProfile
    ) -> PersonaDocument:
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
        fp = self._compute_fingerprint(persona)
        existing = _run(
            PersonaDocument.find_one(PersonaDocument.fingerprint == fp)
        )
        return existing is not None

    def save(self, persona: PersonaProfile) -> bool:
        """Persist a persona (upsert). Returns True if stored, False if duplicate."""
        fp = self._compute_fingerprint(persona)
        existing = _run(
            PersonaDocument.find_one(PersonaDocument.persona_id == persona.persona_id)
        )
        if existing is not None:
            doc = self._doc_from_persona(persona)
            doc.id = existing.id
            _run(doc.save())
            return True

        # Duplicate content guard for new personas.
        duplicate = _run(PersonaDocument.find_one(PersonaDocument.fingerprint == fp))
        if duplicate is not None:
            return False

        doc = self._doc_from_persona(persona)
        _run(doc.insert())
        return True

    def get(self, persona_id: str) -> PersonaProfile | None:
        """Retrieve a persona by ID."""
        doc = _run(PersonaDocument.find_one(PersonaDocument.persona_id == persona_id))
        if doc is None:
            return None
        return self._persona_from_doc(doc)

    def delete(self, persona_id: str) -> bool:
        """Delete a persona by ID."""
        doc = _run(PersonaDocument.find_one(PersonaDocument.persona_id == persona_id))
        if doc is None:
            return False
        _run(doc.delete())
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
        query: Any = {}
        if segment is not None:
            query["segment"] = segment
        if city_tier is not None:
            query["city"] = city_tier
        if bias_status is not None:
            query["bias_audit_status"] = bias_status

        docs = _run(PersonaDocument.find(query).to_list())
        items = [self._persona_from_doc(d) for d in docs]

        if study_id is not None:
            prefix = f"persona-{study_id}-"
            items = [p for p in items if p.persona_id.startswith(prefix)]

        total = len(items)
        start = (page - 1) * page_size
        end = start + page_size
        return items[start:end], total

    def delete_by_study(self, study_id: str) -> int:
        """Delete all personas belonging to a study."""
        prefix = f"persona-{study_id}-"
        docs = _run(PersonaDocument.find({"persona_id": {"$regex": f"^{prefix}"}}).to_list())
        for doc in docs:
            _run(doc.delete())
        return len(docs)

    def count(self) -> int:
        """Total number of stored personas."""
        return _run(PersonaDocument.count())

    def clear(self) -> None:
        """Delete all personas."""
        _run(PersonaDocument.delete_all())


class MongoQuestionnaireStore:
    """MongoDB-backed study and questionnaire store."""

    def save_study(self, study: CBCStudy) -> None:
        """Persist a study (upsert)."""
        doc = _run(StudyDocument.find_one(StudyDocument.study_id == study.study_id))
        data = study.model_dump(mode="json")
        if doc is not None:
            doc.data = data
            doc.status = study.status.value
            _run(doc.save())
        else:
            _run(
                StudyDocument(
                    study_id=study.study_id,
                    product_category=study.product_category,
                    status=study.status.value,
                    data=data,
                ).insert()
            )

    def get_study(self, study_id: str) -> CBCStudy | None:
        """Retrieve a study by ID."""
        doc = _run(StudyDocument.find_one(StudyDocument.study_id == study_id))
        if doc is None:
            return None
        return CBCStudy.model_validate(doc.data)

    def delete_study(self, study_id: str) -> bool:
        """Delete a study and its questionnaire."""
        study_doc = _run(StudyDocument.find_one(StudyDocument.study_id == study_id))
        if study_doc is None:
            return False
        _run(study_doc.delete())
        questionnaire = _run(
            QuestionnaireDocument.find_one(QuestionnaireDocument.study_id == study_id)
        )
        if questionnaire is not None:
            _run(questionnaire.delete())
        return True

    def list_studies(
        self,
        *,
        product_category: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[CBCStudy], int]:
        """Query studies with optional filters."""
        query: Any = {}
        if product_category is not None:
            query["product_category"] = product_category

        docs = _run(StudyDocument.find(query).to_list())
        items = [CBCStudy.model_validate(d.data) for d in docs]
        total = len(items)
        start = (page - 1) * page_size
        end = start + page_size
        return items[start:end], total

    def save_questionnaire(self, questionnaire: CBCQuestionnaire) -> None:
        """Persist a questionnaire keyed by study_id."""
        doc = _run(
            QuestionnaireDocument.find_one(
                QuestionnaireDocument.study_id == questionnaire.study_id
            )
        )
        data = questionnaire.model_dump(mode="json")
        if doc is not None:
            doc.data = data
            doc.questionnaire_id = questionnaire.questionnaire_id
            _run(doc.save())
        else:
            _run(
                QuestionnaireDocument(
                    questionnaire_id=questionnaire.questionnaire_id,
                    study_id=questionnaire.study_id,
                    data=data,
                ).insert()
            )

    def get_questionnaire(self, study_id: str) -> CBCQuestionnaire | None:
        """Retrieve the questionnaire for a study."""
        doc = _run(
            QuestionnaireDocument.find_one(QuestionnaireDocument.study_id == study_id)
        )
        if doc is None:
            return None
        return CBCQuestionnaire.model_validate(doc.data)

    def clear(self) -> None:
        """Delete all studies and questionnaires."""
        _run(StudyDocument.delete_all())
        _run(QuestionnaireDocument.delete_all())


class MongoResponseStore:
    """MongoDB-backed response and dataset store."""

    def save_response(self, response: PersonaResponse) -> None:
        """Persist a single persona response."""
        doc = _run(
            ResponseDocument.find_one(
                ResponseDocument.response_id == response.response_id
            )
        )
        data = response.model_dump(mode="json")
        if doc is not None:
            doc.data = data
            doc.study_id = response.study_id
            doc.persona_id = response.persona_id
            _run(doc.save())
        else:
            _run(
                ResponseDocument(
                    response_id=response.response_id,
                    study_id=response.study_id,
                    persona_id=response.persona_id,
                    data=data,
                ).insert()
            )

    def get_response(self, response_id: str) -> PersonaResponse | None:
        """Retrieve a response by ID."""
        doc = _run(
            ResponseDocument.find_one(ResponseDocument.response_id == response_id)
        )
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
        docs = _run(
            ResponseDocument.find(ResponseDocument.study_id == study_id).to_list()
        )
        items = [PersonaResponse.model_validate(d.data) for d in docs]
        total = len(items)
        start = (page - 1) * page_size
        end = start + page_size
        return items[start:end], total

    def save_dataset(self, study_id: str, dataset: CBCRawDataset) -> None:
        """Persist (or merge) a raw dataset for a study."""
        doc = _run(DatasetDocument.find_one(DatasetDocument.study_id == study_id))
        if doc is not None:
            existing = CBCRawDataset.model_validate(doc.data)
            merged_records = existing.choice_records + dataset.choice_records
            existing.choice_records = merged_records
            existing.metadata.n_respondents += dataset.metadata.n_respondents
            doc.data = existing.model_dump(mode="json")
            doc.updated_at = datetime.now(UTC)
            _run(doc.save())
        else:
            _run(
                DatasetDocument(
                    study_id=study_id,
                    data=dataset.model_dump(mode="json"),
                ).insert()
            )

    def get_dataset(self, study_id: str) -> CBCRawDataset | None:
        """Retrieve the raw dataset for a study."""
        doc = _run(DatasetDocument.find_one(DatasetDocument.study_id == study_id))
        if doc is None:
            return None
        return CBCRawDataset.model_validate(doc.data)

    def delete_response(self, response_id: str) -> bool:
        """Delete a single response by ID."""
        doc = _run(
            ResponseDocument.find_one(ResponseDocument.response_id == response_id)
        )
        if doc is None:
            return False
        _run(doc.delete())
        return True

    def delete_dataset(self, study_id: str) -> bool:
        """Delete the raw dataset for a study."""
        doc = _run(DatasetDocument.find_one(DatasetDocument.study_id == study_id))
        if doc is None:
            return False
        _run(doc.delete())
        return True

    def delete_by_study(self, study_id: str) -> int:
        """Delete all responses and the dataset for a study."""
        response_docs = _run(
            ResponseDocument.find(ResponseDocument.study_id == study_id).to_list()
        )
        for doc in response_docs:
            _run(doc.delete())
        dataset_deleted = self.delete_dataset(study_id)
        return len(response_docs) + (1 if dataset_deleted else 0)

    def delete_by_persona(self, persona_id: str) -> int:
        """Delete all responses belonging to a persona."""
        docs = _run(
            ResponseDocument.find(ResponseDocument.persona_id == persona_id).to_list()
        )
        for doc in docs:
            _run(doc.delete())
        return len(docs)

    def clear(self) -> None:
        """Delete all responses and datasets."""
        _run(ResponseDocument.delete_all())
        _run(DatasetDocument.delete_all())


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
        doc = _run(
            AnalysisJobDocument.find_one(
                AnalysisJobDocument.analysis_id == job.analysis_id
            )
        )
        data = job.model_dump(mode="json")
        if doc is not None:
            doc.data = data
            doc.status = job.status
            _run(doc.save())
        else:
            _run(
                AnalysisJobDocument(
                    analysis_id=job.analysis_id,
                    study_id=job.study_id,
                    status=job.status,
                    data=data,
                ).insert()
            )

    def get_job(self, analysis_id: str) -> AnalysisJobStatus | None:
        """Retrieve a job by ID."""
        doc = _run(
            AnalysisJobDocument.find_one(
                AnalysisJobDocument.analysis_id == analysis_id
            )
        )
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
        doc = _run(
            AnalysisJobDocument.find_one(
                AnalysisJobDocument.analysis_id == analysis_id
            )
        )
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
        if status == "COMPLETED":
            job.completed_at = datetime.now(UTC)
        if progress is not None:
            job.progress_percent = progress

        doc.data = job.model_dump(mode="json")
        doc.status = job.status
        _run(doc.save())
        return job

    def save_result(self, result: AnalysisResultResponse) -> None:
        """Persist a complete analysis result."""
        doc = _run(
            AnalysisResultDocument.find_one(
                AnalysisResultDocument.analysis_id == result.analysis_id
            )
        )
        data = result.model_dump(mode="json")
        if doc is not None:
            doc.data = data
            _run(doc.save())
        else:
            _run(
                AnalysisResultDocument(
                    analysis_id=result.analysis_id,
                    study_id=result.study_id,
                    data=data,
                ).insert()
            )

    def get_result(self, analysis_id: str) -> AnalysisResultResponse | None:
        """Retrieve a complete analysis result."""
        doc = _run(
            AnalysisResultDocument.find_one(
                AnalysisResultDocument.analysis_id == analysis_id
            )
        )
        if doc is None:
            return None
        return AnalysisResultResponse.model_validate(doc.data)

    def save_convergence(
        self, analysis_id: str, diag: ConvergenceDiagnostics
    ) -> None:
        """Persist convergence diagnostics."""
        _run(
            self._save_derivative(
                analysis_id, "convergence", None, diag.model_dump(mode="json")
            )
        )

    def get_convergence(self, analysis_id: str) -> ConvergenceDiagnostics | None:
        """Retrieve convergence diagnostics."""
        doc = _run(self._get_derivative(analysis_id, "convergence", None))
        if doc is None:
            return None
        return ConvergenceDiagnostics.model_validate(doc.data)

    def save_importance(
        self, analysis_id: str, importance: ImportanceResponse
    ) -> None:
        """Persist attribute importance results."""
        _run(
            self._save_derivative(
                analysis_id, "importance", None, importance.model_dump(mode="json")
            )
        )

    def get_importance(self, analysis_id: str) -> ImportanceResponse | None:
        """Retrieve attribute importance results."""
        doc = _run(self._get_derivative(analysis_id, "importance", None))
        if doc is None:
            return None
        return ImportanceResponse.model_validate(doc.data)

    def save_wtp(self, analysis_id: str, wtp: WTPResponse) -> None:
        """Persist WTP results."""
        _run(
            self._save_derivative(
                analysis_id, "wtp", None, wtp.model_dump(mode="json")
            )
        )

    def get_wtp(self, analysis_id: str) -> WTPResponse | None:
        """Retrieve WTP results."""
        doc = _run(self._get_derivative(analysis_id, "wtp", None))
        if doc is None:
            return None
        return WTPResponse.model_validate(doc.data)

    def save_market_sim(
        self, analysis_id: str, sim_id: str, result: MarketSimResponse
    ) -> None:
        """Persist market simulation result keyed by analysis_id + sim_id."""
        _run(
            self._save_derivative(
                analysis_id,
                "market_sim",
                sim_id,
                result.model_dump(mode="json"),
            )
        )

    def get_market_sim(
        self, analysis_id: str, sim_id: str
    ) -> MarketSimResponse | None:
        """Retrieve market simulation result."""
        doc = _run(self._get_derivative(analysis_id, "market_sim", sim_id))
        if doc is None:
            return None
        return MarketSimResponse.model_validate(doc.data)

    def get_latest_market_sim(self, analysis_id: str) -> MarketSimResponse | None:
        """Return the most recent market simulation for an analysis."""
        docs = _run(
            AnalysisDerivativeDocument.find(
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

    def save_latent_class_result(
        self, analysis_id: str, result: dict[str, Any]
    ) -> None:
        """Store a latent class model result."""
        _run(
            self._save_derivative(
                analysis_id,
                "latent_class",
                None,
                result,
            )
        )

    def get_latent_class_result(
        self, analysis_id: str
    ) -> dict[str, Any] | None:
        """Retrieve a latent class model result."""
        doc = _run(self._get_derivative(analysis_id, "latent_class", None))
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
        key = f"{segment_a}:{segment_b}"
        _run(
            self._save_derivative(
                analysis_id,
                "segment_comparison",
                key,
                result.model_dump(mode="json"),
            )
        )

    def get_segment_comparison(
        self,
        analysis_id: str,
        segment_a: str | None = None,
        segment_b: str | None = None,
    ) -> SegmentComparisonResponse | None:
        """Retrieve segment comparison result."""
        if segment_a is not None and segment_b is not None:
            key = f"{segment_a}:{segment_b}"
            doc = _run(self._get_derivative(analysis_id, "segment_comparison", key))
            if doc is None:
                return None
            return SegmentComparisonResponse.model_validate(doc.data)

        # Backward-compatible prefix scan.
        docs = _run(
            AnalysisDerivativeDocument.find(
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

    async def _save_derivative(
        self,
        analysis_id: str,
        kind: str,
        key: str | None,
        data: dict[str, Any],
    ) -> None:
        """Upsert a derivative artefact (async helper)."""
        job_doc = await AnalysisJobDocument.find_one(
            AnalysisJobDocument.analysis_id == analysis_id
        )
        study_id = job_doc.study_id if job_doc is not None else ""
        doc = await AnalysisDerivativeDocument.find_one(
            {
                "analysis_id": analysis_id,
                "kind": kind,
                "key": key,
            }
        )
        if doc is not None:
            doc.data = data
            doc.created_at = datetime.now(UTC)
            await doc.save()
        else:
            await AnalysisDerivativeDocument(
                analysis_id=analysis_id,
                study_id=study_id,
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
        """Fetch a derivative artefact (async helper)."""
        return await AnalysisDerivativeDocument.find_one(
            {
                "analysis_id": analysis_id,
                "kind": kind,
                "key": key,
            }
        )

    def list_jobs_by_study(self, study_id: str) -> list[AnalysisJobStatus]:
        """Return all analysis jobs belonging to a study."""
        docs = _run(
            AnalysisJobDocument.find(
                AnalysisJobDocument.study_id == study_id
            ).to_list()
        )
        return [AnalysisJobStatus.model_validate(doc.data) for doc in docs]

    def delete_analysis(self, analysis_id: str) -> bool:
        """Delete a job, its result, and all derivative artefacts."""
        job_doc = _run(
            AnalysisJobDocument.find_one(
                AnalysisJobDocument.analysis_id == analysis_id
            )
        )
        if job_doc is None:
            return False

        _run(job_doc.delete())

        result_doc = _run(
            AnalysisResultDocument.find_one(
                AnalysisResultDocument.analysis_id == analysis_id
            )
        )
        if result_doc is not None:
            _run(result_doc.delete())

        derivative_docs = _run(
            AnalysisDerivativeDocument.find(
                AnalysisDerivativeDocument.analysis_id == analysis_id
            ).to_list()
        )
        for doc in derivative_docs:
            _run(doc.delete())
        return True

    def delete_by_study(self, study_id: str) -> int:
        """Delete all analyses belonging to a study."""
        docs = _run(
            AnalysisJobDocument.find(AnalysisJobDocument.study_id == study_id).to_list()
        )
        for doc in docs:
            self.delete_analysis(doc.analysis_id)
        return len(docs)

    def clear(self) -> None:
        """Delete all analysis data."""
        _run(AnalysisJobDocument.delete_all())
        _run(AnalysisResultDocument.delete_all())
        _run(AnalysisDerivativeDocument.delete_all())
