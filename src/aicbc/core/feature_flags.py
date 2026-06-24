"""Simple feature flag store backed by memory or MongoDB.

The memory store is used for local development/tests; MongoDB is used in
staging/production when ``MONGODB_URL`` is configured.  Flags are scoped by
``(name, environment)`` so the same workflow can target staging or production.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from aicbc.core.store import _use_memory_store


@dataclass
class FeatureFlag:
    name: str
    enabled: bool = False
    environment: str = "staging"
    updated_by: str = "system"
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "environment": self.environment,
            "updated_by": self.updated_by,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FeatureFlag:
        return cls(
            name=data["name"],
            enabled=data.get("enabled", False),
            environment=data.get("environment", "staging"),
            updated_by=data.get("updated_by", "system"),
            updated_at=data.get("updated_at", datetime.now(UTC).isoformat()),
        )


class MemoryFeatureFlagStore:
    """Thread-safe in-memory store for feature flags."""

    def __init__(self) -> None:
        self._flags: dict[str, FeatureFlag] = {}

    async def aget(self, name: str, environment: str) -> FeatureFlag | None:
        return self._flags.get(f"{environment}:{name}")

    async def aset(self, flag: FeatureFlag) -> None:
        self._flags[f"{flag.environment}:{flag.name}"] = flag

    async def alist(self, environment: str | None = None) -> list[FeatureFlag]:
        if environment is None:
            return list(self._flags.values())
        return [f for f in self._flags.values() if f.environment == environment]


class MongoFeatureFlagStore:
    """MongoDB-backed store for feature flags using Beanie."""

    async def aget(self, name: str, environment: str) -> FeatureFlag | None:
        from aicbc.core.models.db_documents import FeatureFlagDocument

        doc = await FeatureFlagDocument.find_one(
            FeatureFlagDocument.name == name,
            FeatureFlagDocument.environment == environment,
        )
        if doc is None:
            return None
        return FeatureFlag(
            name=doc.name,
            enabled=doc.enabled,
            environment=doc.environment,
            updated_by=doc.updated_by,
            updated_at=doc.updated_at.isoformat(),
        )

    async def aset(self, flag: FeatureFlag) -> None:
        from aicbc.core.models.db_documents import FeatureFlagDocument

        existing = await FeatureFlagDocument.find_one(
            FeatureFlagDocument.name == flag.name,
            FeatureFlagDocument.environment == flag.environment,
        )
        updated_at = (
            datetime.fromisoformat(flag.updated_at) if flag.updated_at else datetime.now(UTC)
        )
        if existing is not None:
            existing.enabled = flag.enabled
            existing.updated_by = flag.updated_by
            existing.updated_at = updated_at
            await existing.save()
        else:
            doc = FeatureFlagDocument(
                name=flag.name,
                environment=flag.environment,
                enabled=flag.enabled,
                updated_by=flag.updated_by,
                updated_at=updated_at,
            )
            await doc.insert()

    async def alist(self, environment: str | None = None) -> list[FeatureFlag]:
        from aicbc.core.models.db_documents import FeatureFlagDocument

        query: Any = {}
        if environment is not None:
            query["environment"] = environment
        docs = await FeatureFlagDocument.find(query).to_list()
        return [
            FeatureFlag(
                name=doc.name,
                enabled=doc.enabled,
                environment=doc.environment,
                updated_by=doc.updated_by,
                updated_at=doc.updated_at.isoformat(),
            )
            for doc in docs
        ]


_feature_store: MemoryFeatureFlagStore | MongoFeatureFlagStore | None = None


def get_feature_flag_store() -> MemoryFeatureFlagStore | MongoFeatureFlagStore:
    """Return the global feature flag store singleton."""
    global _feature_store
    if _feature_store is None:
        if _use_memory_store():
            _feature_store = MemoryFeatureFlagStore()
        else:
            _feature_store = MongoFeatureFlagStore()
    return _feature_store
