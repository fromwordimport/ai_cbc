"""Audit logging for AI_CBC.

Provides an async ``AuditLogger`` that persists security-relevant events to
MongoDB via ``AuditLogDocument``. When MongoDB is unavailable (in-memory mode
or during tests), events are kept in a bounded in-memory deque so audit
behaviour can still be verified.
"""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import Request

from aicbc.core.models.db_documents import AuditLogDocument
from aicbc.core.privacy import redact_dict

logger = structlog.get_logger("aicbc.core.audit")

_MAX_MEMORY_ENTRIES = 1000


class AuditLogger:
    """Async audit logger with MongoDB primary storage and memory fallback."""

    def __init__(self, max_memory_entries: int = _MAX_MEMORY_ENTRIES) -> None:
        self._memory: deque[dict[str, Any]] = deque(maxlen=max_memory_entries)

    async def log_event(
        self,
        action: str,
        resource: str,
        resource_id: str,
        result: str,
        request: Request | None = None,
        user_id: str = "anonymous",
        data: dict[str, Any] | None = None,
    ) -> None:
        """Persist an audit log entry.

        Args:
            action: HTTP method or high-level action name (e.g. ``POST``,
                ``DELETE``, ``auth_failure``).
            resource: Resource type being acted on (e.g. ``personas``,
                ``studies``).
            resource_id: Identifier of the specific resource.
            result: Outcome string such as ``success``, ``denied``, ``error``.
            request: Optional FastAPI request for IP/header extraction.
            user_id: Acting user identifier.
            data: Additional structured context.
        """
        entry = self._build_entry(
            action=action,
            resource=resource,
            resource_id=resource_id,
            result=result,
            request=request,
            user_id=user_id,
            data=data or {},
        )

        try:
            await AuditLogDocument(**entry).insert()
        except Exception as exc:
            # Fallback to memory when MongoDB/Beanie is not initialized.
            logger.warning(
                "audit_log_mongodb_unavailable",
                error=str(exc),
                action=action,
                resource=resource,
            )
            self._memory.append(entry)

    def _build_entry(
        self,
        action: str,
        resource: str,
        resource_id: str,
        result: str,
        request: Request | None,
        user_id: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Construct a normalized audit log entry."""
        ip_address = "unknown"
        user_agent = ""
        role = ""

        if request is not None:
            forwarded = request.headers.get("X-Forwarded-For")
            if forwarded:
                ip_address = forwarded.split(",")[0].strip()
            else:
                real_ip = request.headers.get("X-Real-IP")
                if real_ip:
                    ip_address = real_ip.strip()
                elif request.client and request.client.host:
                    ip_address = request.client.host
            user_agent = request.headers.get("User-Agent", "")
            role = request.headers.get("X-User-Role", "")
            user_id = request.headers.get("X-User-Id", user_id)

        return {
            "timestamp": datetime.now(UTC),
            "user_id": user_id,
            "action": action,
            "resource": resource,
            "resource_id": resource_id,
            "result": result,
            "ip_address": ip_address,
            "data": redact_dict(
                {
                    **data,
                    "user_agent": user_agent,
                    "role": role,
                }
            ),
        }

    def get_memory_logs(self) -> list[dict[str, Any]]:
        """Return in-memory audit entries (useful for tests/dev mode)."""
        return list(self._memory)

    def clear_memory_logs(self) -> None:
        """Clear the in-memory audit buffer."""
        self._memory.clear()

    async def query_logs(
        self,
        filters: dict[str, Any],
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """Query audit logs with filters and pagination.

        Uses MongoDB when available, otherwise falls back to the in-memory
        buffer. Returns a tuple of (entries_for_page, total_count).
        """
        try:
            return await self._query_mongo_logs(filters, page, page_size)
        except Exception as exc:
            logger.warning(
                "audit_log_query_mongodb_unavailable",
                error=str(exc),
                filters=filters,
            )
            return self._query_memory_logs(filters, page, page_size)

    async def _query_mongo_logs(
        self,
        filters: dict[str, Any],
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        """Query audit logs from MongoDB via Beanie."""
        query: dict[str, Any] = {}
        start_time = filters.get("start_time")
        end_time = filters.get("end_time")
        if start_time is not None or end_time is not None:
            time_query: dict[str, Any] = {}
            if start_time is not None:
                time_query["$gte"] = start_time
            if end_time is not None:
                time_query["$lte"] = end_time
            query["timestamp"] = time_query
        for key in ("user_id", "action", "resource", "result"):
            value = filters.get(key)
            if value is not None:
                query[key] = value

        total = await AuditLogDocument.find(query).count()
        docs = (
            await AuditLogDocument.find(query)
            .sort(-AuditLogDocument.timestamp)
            .skip((page - 1) * page_size)
            .limit(page_size)
            .to_list()
        )
        entries = [
            {
                "timestamp": doc.timestamp,
                "user_id": doc.user_id,
                "action": doc.action,
                "resource": doc.resource,
                "resource_id": doc.resource_id,
                "result": doc.result,
                "ip_address": doc.ip_address,
                "data": doc.data,
            }
            for doc in docs
        ]
        return entries, total

    def _query_memory_logs(
        self,
        filters: dict[str, Any],
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        """Query audit logs from the in-memory buffer."""
        start_time = filters.get("start_time")
        end_time = filters.get("end_time")

        def _matches(entry: dict[str, Any]) -> bool:
            if start_time is not None and entry["timestamp"] < start_time:
                return False
            if end_time is not None and entry["timestamp"] > end_time:
                return False
            for key in ("user_id", "action", "resource", "result"):
                value = filters.get(key)
                if value is not None and entry.get(key) != value:
                    return False
            return True

        all_entries = [e for e in self._memory if _matches(e)]
        all_entries.sort(key=lambda e: e["timestamp"], reverse=True)
        total = len(all_entries)
        start = (page - 1) * page_size
        end = start + page_size
        return all_entries[start:end], total


# Module-level singleton for middleware and route use.
_default_logger: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    """Return the shared audit logger instance."""
    global _default_logger
    if _default_logger is None:
        _default_logger = AuditLogger()
    return _default_logger


def reset_audit_logger() -> None:
    """Reset the shared logger and clear its memory buffer."""
    global _default_logger
    _default_logger = AuditLogger()
