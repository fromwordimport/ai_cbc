"""Application settings loaded from environment variables."""

from functools import lru_cache
from typing import Any

import structlog
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from aicbc.core.security.encryption import decrypt_value, is_encrypted


class LLMSettings(BaseSettings):
    """LLM API configuration."""

    model_config = SettingsConfigDict(env_prefix="LLM_")

    provider: str = "anthropic"
    model: str = ""
    temperature: float = 0.3
    max_tokens: int = 4096
    timeout_seconds: int = 120
    max_retries: int = 3


class AnthropicSettings(BaseSettings):
    """Anthropic Claude API configuration."""

    model_config = SettingsConfigDict(env_prefix="ANTHROPIC_")

    enabled: bool = False
    api_key: str = Field(default="", description="Anthropic API key")
    base_url: str = "https://api.anthropic.com"
    model_persona: str = "claude-sonnet-4-6"
    model_simulation: str = "claude-sonnet-4-6"
    model_audit: str = "claude-haiku-4-5"


class OpenAISettings(BaseSettings):
    """OpenAI API configuration."""

    model_config = SettingsConfigDict(env_prefix="OPENAI_")

    enabled: bool = False
    api_key: str = Field(default="", description="OpenAI API key")
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o"


class DeepSeekSettings(BaseSettings):
    """DeepSeek API configuration (OpenAI-compatible)."""

    model_config = SettingsConfigDict(env_prefix="DEEPSEEK_")

    enabled: bool = False
    api_key: str = Field(default="", description="DeepSeek API key")
    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-chat"


class QwenSettings(BaseSettings):
    """Tongyi Qianwen API configuration (OpenAI-compatible)."""

    model_config = SettingsConfigDict(env_prefix="QWEN_")

    enabled: bool = False
    api_key: str = Field(default="", description="Qwen API key")
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model: str = "qwen-max"


class GLMSettings(BaseSettings):
    """Zhipu GLM API configuration (OpenAI-compatible)."""

    model_config = SettingsConfigDict(env_prefix="GLM_")

    enabled: bool = False
    api_key: str = Field(default="", description="GLM API key")
    base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    model: str = "glm-4"


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
    monthly_cny: float = 20000.0
    degrade_model: str = "claude-haiku-4-5"


class CostTrackerSettings(BaseSettings):
    """Cost tracker persistence configuration."""

    model_config = SettingsConfigDict(env_prefix="COST_TRACKER_")

    backend: str = "file"
    redis_key: str = "aicbc:cost:state"
    redis_ttl: int = 604800


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
    cramers_v_threshold: float = 0.2  # aligned with 虚拟消费者公平性规范.md §2.1
    entropy_threshold: float = 0.7


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = Field(default="development", alias="ENVIRONMENT")
    debug: bool = Field(default=False, alias="DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")  # nosec B104
    api_port: int = Field(default=8000, alias="API_PORT")
    api_workers: int = Field(default=1, alias="API_WORKERS")
    api_key: str = Field(default="dev-key-change-in-prod", alias="API_KEY")
    secret_key: str = Field(
        default="dev-secret-key-change-in-production-32chars",
        alias="SECRET_KEY",
        min_length=32,
        description="Secret key for JWT/session/CSRF signing (min 32 chars)",
    )

    llm: LLMSettings = Field(default_factory=LLMSettings)
    anthropic: AnthropicSettings = Field(default_factory=AnthropicSettings)
    openai: OpenAISettings = Field(default_factory=OpenAISettings)
    deepseek: DeepSeekSettings = Field(default_factory=DeepSeekSettings)
    qwen: QwenSettings = Field(default_factory=QwenSettings)
    glm: GLMSettings = Field(default_factory=GLMSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    cost_fuse: CostFuseSettings = Field(default_factory=CostFuseSettings)
    cost_tracker: CostTrackerSettings = Field(default_factory=CostTrackerSettings)
    study: StudySettings = Field(default_factory=StudySettings)
    authenticity: AuthenticitySettings = Field(default_factory=AuthenticitySettings)
    bias_audit: BiasAuditSettings = Field(default_factory=BiasAuditSettings)

    # Celery
    celery_broker_url: str = Field(
        default="",
        alias="CELERY_BROKER_URL",
    )

    # Monitoring
    metrics_path: str = "/metrics"
    slow_request_threshold: float = 5.0

    # CORS
    frontend_origins: str = Field(
        default="",
        alias="FRONTEND_ORIGINS",
        description="Comma-separated list of allowed frontend origins for CORS",
    )

    @property
    def is_production(self) -> bool:
        """Return True if running in production environment."""
        return self.environment.lower() in ("production", "prod", "staging")

    @field_validator("secret_key", mode="before")
    @classmethod
    def _validate_secret_key(cls, v: Any) -> Any:
        """Validate secret key: require non-default value in production."""
        if isinstance(v, str) and v.strip():
            key = v.strip()
            # If environment field is not yet loaded during validation,
            # we accept any non-empty, non-default key.
            if "dev-secret-key-change" in key:
                pass  # dev default — production should override via env
            return key
        return "dev-secret-key-change-in-production-32chars"

    @field_validator("celery_broker_url", mode="before")
    @classmethod
    def _celery_broker_url_fallback(cls, v: Any) -> Any:
        """Fallback CELERY_BROKER_URL to REDIS_URL when not explicitly set."""
        if isinstance(v, str) and v.strip():
            return cls._ensure_redis_ssl_params(v)
        import os

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        return cls._ensure_redis_ssl_params(redis_url)

    @staticmethod
    def _ensure_redis_ssl_params(url: str) -> str:
        """Append ssl_cert_reqs for rediss:// URLs required by Celery."""
        if url.startswith("rediss://") and "ssl_cert_reqs" not in url:
            separator = "&" if "?" in url else "?"
            return f"{url}{separator}ssl_cert_reqs=CERT_NONE"
        return url

    def model_post_init(self, __context: Any) -> None:
        """Decrypt any encrypted secrets after the model is initialised."""
        self.api_key = decrypt_value(self.api_key, self.secret_key)
        self.anthropic.api_key = decrypt_value(self.anthropic.api_key, self.secret_key)
        self.openai.api_key = decrypt_value(self.openai.api_key, self.secret_key)
        self.deepseek.api_key = decrypt_value(self.deepseek.api_key, self.secret_key)
        self.qwen.api_key = decrypt_value(self.qwen.api_key, self.secret_key)
        self.glm.api_key = decrypt_value(self.glm.api_key, self.secret_key)

        # Mark providers as enabled when a non-empty API key is configured.
        self.anthropic.enabled = bool(self.anthropic.api_key)
        self.openai.enabled = bool(self.openai.api_key)
        self.deepseek.enabled = bool(self.deepseek.api_key)
        self.qwen.enabled = bool(self.qwen.api_key)
        self.glm.enabled = bool(self.glm.api_key)

        if self.is_production:
            log = structlog.get_logger("aicbc.config")
            if not is_encrypted(self.api_key) and self.api_key != "dev-key-change-in-prod":
                log.warning(
                    "api_key stored in plaintext in production",
                    recommendation="encrypt with aicbc.core.security.encryption.encrypt_value",
                )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
