"""Central environment-backed configuration with production safeguards."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEVELOPMENT_SECRET = "proofstack-development-only-secret-change-before-production"  # noqa: S105 - Rejected in production.


class Settings(BaseSettings):
    """Runtime settings shared by API, worker, providers, and CLI."""

    model_config = SettingsConfigDict(
        env_prefix="PROOFSTACK_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Literal["development", "test", "production"] = "development"
    demo_mode: bool = True
    database_url: str = "sqlite:///./proofstack.db"
    redis_url: str = "redis://localhost:6379/0"
    task_backend: Literal["inline", "rq"] = "inline"
    runner: Literal["native", "docker"] = "native"
    secret_key: SecretStr = SecretStr(DEVELOPMENT_SECRET)
    access_token_ttl: int = Field(default=900, ge=60, le=86400)
    refresh_token_ttl: int = Field(default=604800, ge=300, le=2592000)
    max_upload_mb: int = Field(default=25, ge=1, le=500)
    max_repository_mb: int = Field(default=100, ge=1, le=5000)
    max_file_count: int = Field(default=10000, ge=1, le=500000)
    command_timeout: int = Field(default=120, ge=1, le=3600)
    github_token: SecretStr | None = None
    semgrep_enabled: bool = False
    llm_enabled: bool = False
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: SecretStr | None = None
    llm_model: str = ""
    allowed_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://localhost:8080",
    ]
    artifact_root: Path = Path(".proofstack/artifacts")
    workspace_root: Path = Path(".proofstack/workspaces")
    log_level: str = "INFO"

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def validate_security_boundary(self) -> "Settings":
        secret = self.secret_key.get_secret_value()
        if self.env == "production" and (
            secret == DEVELOPMENT_SECRET or len(secret.encode("utf-8")) < 32
        ):
            raise ValueError(
                "PROOFSTACK_SECRET_KEY must be replaced by at least 32 random bytes in production"
            )
        if self.env == "production" and self.demo_mode:
            raise ValueError("PROOFSTACK_DEMO_MODE must be disabled in production")
        if self.env == "production" and "*" in self.allowed_origins:
            raise ValueError("Wildcard CORS origins are not allowed in production")
        if self.llm_enabled and (self.llm_api_key is None or not self.llm_model):
            raise ValueError("LLM mode requires an API key and model")
        return self

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def max_repository_bytes(self) -> int:
        return self.max_repository_mb * 1024 * 1024


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return one validated settings instance per process."""

    return Settings()
