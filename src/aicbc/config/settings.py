"""Application settings loaded from environment variables."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """LLM API configuration."""

    model_config = SettingsConfigDict(env_prefix="LLM_")

    temperature: float = 0.3
    max_tokens: int = 4096
    timeout_seconds: int = 120
    max_retries: int = 3


class AnthropicSettings(BaseSettings):
    """Anthropic Claude API configuration."""

    model_config = SettingsConfigDict(env_prefix="ANTHROPIC_")

    api_key: str = Field(default="", description="Anthropic API key")
    base_url: str = "https://api.anthropic.com"
    model_persona: str = "claude-sonnet-4-6"
    model_simulation: str = "claude-sonnet-4-6"
    model_audit: str = "claude-haiku-4-5"


class OpenAISettings(BaseSettings):
    """OpenAI API configuration."""

    model_config = SettingsConfigDict(env_prefix="OPENAI_")

    api_key: str = Field(default="", description="OpenAI API key")
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o"


class DatabaseSettings(BaseSettings):
    """Database configuration."""

    mongodb_url: str = Field(default="mongodb://localhost:27017", alias="MONGODB_URL")
    mongodb_database: str = Field(default="aicbc", alias="MONGODB_DATABASE")
    mongodb_max_connections: int = Field(default=50, alias="MONGODB_MAX_CONNECTIONS")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    redis_password: str = Field(default="", alias="REDIS_PASSWORD")


class CostFuseSettings(BaseSettings):
    """Cost fuse configuration."""

    model_config = SettingsConfigDict(env_prefix="COST_FUSE_")

    single_study_cny: float = 500.0
    daily_cny: float = 1000.0
    weekly_cny: float = 5000.0
    degrade_model: str = "claude-haiku-4-5"


class StudySettings(BaseSettings):
    """Default study parameters."""

    model_config = SettingsConfigDict(env_prefix="DEFAULT_")

    n_choice_sets: int = 12
    n_alternatives: int = 3
    sample_size: int = 150
    d_efficiency_target: float = 0.85


class AuthenticitySettings(BaseSettings):
    """Authenticity scoring thresholds."""

    model_config = SettingsConfigDict(env_prefix="AUTHENTICITY_")

    pass_threshold: int = 9
    excellent_threshold: int = 12
    max_score: int = 14


class BiasAuditSettings(BaseSettings):
    """Bias audit thresholds."""

    model_config = SettingsConfigDict(env_prefix="BIAS_")

    ks_p_threshold: float = 0.05
    cramers_v_threshold: float = 0.1
    entropy_threshold: float = 0.7


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = Field(default="development", alias="ENVIRONMENT")
    debug: bool = Field(default=True, alias="DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    api_workers: int = Field(default=1, alias="API_WORKERS")
    secret_key: str = Field(default="change-me", alias="SECRET_KEY")

    llm: LLMSettings = Field(default_factory=LLMSettings)
    anthropic: AnthropicSettings = Field(default_factory=AnthropicSettings)
    openai: OpenAISettings = Field(default_factory=OpenAISettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    cost_fuse: CostFuseSettings = Field(default_factory=CostFuseSettings)
    study: StudySettings = Field(default_factory=StudySettings)
    authenticity: AuthenticitySettings = Field(default_factory=AuthenticitySettings)
    bias_audit: BiasAuditSettings = Field(default_factory=BiasAuditSettings)

    # Monitoring
    metrics_path: str = "/metrics"
    slow_request_threshold: float = 5.0


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
