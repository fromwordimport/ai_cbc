"""FastAPI dependency injection for AI_CBC API."""

from __future__ import annotations

import structlog
from fastapi import Request

from aicbc.config.settings import Settings, get_settings
from aicbc.core.validators import LogicValidator, SchemaValidator
from aicbc.generators.profile_generator import ProfileGenerator
from aicbc.generators.seed_generator import SeedGenerator
from aicbc.llm.client import LLMClient

logger = structlog.get_logger("aicbc.api")


# Singleton instances (initialized lazily)
_llm_client: LLMClient | None = None
_seed_generator: SeedGenerator | None = None
_profile_generator: ProfileGenerator | None = None
_schema_validator: SchemaValidator | None = None
_logic_validator: LogicValidator | None = None


def get_llm_client() -> LLMClient:
    """Return a singleton LLMClient instance."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client


def get_seed_generator() -> SeedGenerator:
    """Return a singleton SeedGenerator instance."""
    global _seed_generator
    if _seed_generator is None:
        _seed_generator = SeedGenerator()
    return _seed_generator


def get_profile_generator() -> ProfileGenerator:
    """Return a singleton ProfileGenerator instance."""
    global _profile_generator
    if _profile_generator is None:
        _profile_generator = ProfileGenerator(llm_client=get_llm_client())
    return _profile_generator


def get_schema_validator() -> SchemaValidator:
    """Return a singleton SchemaValidator instance."""
    global _schema_validator
    if _schema_validator is None:
        _schema_validator = SchemaValidator()
    return _schema_validator


def get_logic_validator() -> LogicValidator:
    """Return a singleton LogicValidator instance."""
    global _logic_validator
    if _logic_validator is None:
        _logic_validator = LogicValidator()
    return _logic_validator


def get_settings_dep() -> Settings:
    """Return application settings (FastAPI dependency wrapper)."""
    return get_settings()
