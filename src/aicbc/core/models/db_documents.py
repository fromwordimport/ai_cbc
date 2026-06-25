"""Beanie ODM document models for MongoDB persistence.

Documents store the full serialized Pydantic model in a ``data`` field plus a
small set of indexed top-level fields used for querying.  This keeps the
Document layer thin and avoids duplicating the rich Pydantic schema defined in
``aicbc.core.models.persona`` and ``aicbc.questionnaire.models``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from beanie import Document, Indexed
from pydantic import Field
from pymongo import IndexModel


class PersonaDocument(Document):
    """Persistent storage for ``PersonaProfile``."""

    persona_id: Indexed(str, unique=True)
    fingerprint: Indexed(str)
    segment: Indexed(str)
    city: Indexed(str)
    bias_audit_status: Indexed(str)
    status: Indexed(str)
    data: dict[str, Any]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "personas"


class StudyDocument(Document):
    """Persistent storage for ``CBCStudy``."""

    study_id: Indexed(str, unique=True)
    product_category: Indexed(str)
    status: Indexed(str)
    data: dict[str, Any]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "studies"


class QuestionnaireDocument(Document):
    """Persistent storage for ``CBCQuestionnaire``."""

    questionnaire_id: Indexed(str, unique=True)
    study_id: Indexed(str)
    data: dict[str, Any]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "questionnaires"


class ResponseDocument(Document):
    """Persistent storage for ``PersonaResponse``."""

    response_id: Indexed(str, unique=True)
    study_id: Indexed(str)
    persona_id: Indexed(str)
    data: dict[str, Any]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "responses"


class DatasetDocument(Document):
    """Persistent storage for ``CBCRawDataset`` keyed by study."""

    study_id: Indexed(str, unique=True)
    data: dict[str, Any]
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "datasets"


class AnalysisJobDocument(Document):
    """Persistent storage for ``AnalysisJobStatus``."""

    analysis_id: Indexed(str, unique=True)
    study_id: Indexed(str)
    status: Indexed(str)
    data: dict[str, Any]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "analysis_jobs"
        indexes = [
            IndexModel([("created_at", -1)]),
        ]


class AnalysisResultDocument(Document):
    """Persistent storage for ``AnalysisResultResponse``."""

    analysis_id: Indexed(str, unique=True)
    study_id: Indexed(str)
    data: dict[str, Any]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "analysis_results"
        indexes = [
            IndexModel([("created_at", -1)]),
        ]


class AnalysisDerivativeDocument(Document):
    """Persistent storage for derived analysis artefacts.

    ``kind`` identifies the artefact type (``convergence``, ``importance``,
    ``wtp``, ``market_sim``, ``segment_comparison``).  ``key`` is an optional
    compound key used for artefacts that may have multiple entries per analysis
    (e.g. ``market_sim`` simulations or ``segment_comparison`` pairs).
    """

    analysis_id: Indexed(str)
    study_id: Indexed(str)
    kind: Indexed(str)
    key: str | None = None
    data: dict[str, Any]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "analysis_derivatives"
        indexes = [
            IndexModel(
                [("analysis_id", 1), ("kind", 1), ("key", 1)],
                unique=True,
            ),
        ]


class SettingsDocument(Document):
    """Persistent storage for global runtime settings."""

    settings_id: Indexed(str, unique=True)
    data: dict[str, Any]
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "settings"


class FeatureFlagDocument(Document):
    """Persistent storage for feature flags, keyed by name + environment."""

    name: Indexed(str)
    environment: Indexed(str)
    enabled: bool
    updated_by: str
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "feature_flags"
        indexes = [
            IndexModel([("name", 1), ("environment", 1)], unique=True),
        ]


class AuditLogDocument(Document):
    """Persistent audit log entries."""

    timestamp: Indexed(datetime)
    user_id: Indexed(str)
    action: Indexed(str)
    resource: Indexed(str)
    resource_id: Indexed(str)
    result: str
    ip_address: str
    data: dict[str, Any]

    class Settings:
        name = "audit_logs"
        indexes = [
            IndexModel([("created_at", -1)]),
        ]


class PersonaGenerationJobDocument(Document):
    """Persisted state for async persona generation Celery tasks."""

    job_id: Indexed(str, unique=True)
    study_id: Indexed(str)
    status: Indexed(str)
    requested: int
    generated: int = 0
    failed: int = 0
    total_cost_cny: float = 0.0
    bias_failed_count: int = 0
    bias_warning: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "persona_generation_jobs"
        indexes = [
            IndexModel([("created_at", -1)]),
            IndexModel([("status", 1)]),
        ]


class DeadLetterDocument(Document):
    """Persisted record of failed Celery tasks for later inspection."""

    task_name: str
    analysis_id: str | None = None
    study_id: str | None = None
    exception: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "dead_letters"
        indexes = [
            IndexModel([("created_at", -1)]),
            IndexModel([("task_name", 1)]),
        ]


# Convenience list used during Beanie initialization.
ALL_DOCUMENT_MODELS: list[type[Document]] = [
    PersonaDocument,
    StudyDocument,
    QuestionnaireDocument,
    ResponseDocument,
    DatasetDocument,
    AnalysisJobDocument,
    AnalysisResultDocument,
    AnalysisDerivativeDocument,
    SettingsDocument,
    FeatureFlagDocument,
    AuditLogDocument,
    PersonaGenerationJobDocument,
    DeadLetterDocument,
]
