from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(Path(__file__).resolve().parents[3] / ".env",),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ResearchForge"
    app_env: str = "development"
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    frontend_origin: str = "http://localhost:5173"

    postgres_host: str = "127.0.0.1"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_user: str = "postgres"
    postgres_password: str = Field(repr=False)
    postgres_db: str = "agent"

    redis_host: str = "127.0.0.1"
    redis_port: int = Field(default=6379, ge=1, le=65535)
    redis_db: int = Field(default=0, ge=0)

    chroma_host: str = "127.0.0.1"
    chroma_port: int = Field(default=8001, ge=1, le=65535)
    chroma_data_dir: Path = Path("data/chroma")
    chroma_index_version: str = "1"

    paper_storage_dir: Path = Path("data/papers")
    max_upload_mb: int = Field(default=50, ge=1)
    max_upload_files: int = Field(default=20, ge=1, le=100)

    llm_base_url: str | None = None
    llm_api_key: str | None = Field(default=None, repr=False)
    llm_model: str | None = None
    llm_extraction_model: str | None = None
    llm_timeout_seconds: int = Field(default=300, ge=1, le=3600)
    llm_max_retries: int = Field(default=2, ge=0, le=5)
    llm_output_tokens: int = Field(default=8192, ge=256, le=65536)
    agent_max_revisions: int = Field(default=1, ge=0, le=3)
    rag_top_k: int = Field(default=15, ge=1, le=50)
    rag_concurrency: int = Field(default=3, ge=1, le=8)
    knowledge_batch_chars: int = Field(default=14000, ge=1000, le=64000)
    task_lease_seconds: int = Field(default=120, ge=30)
    task_heartbeat_seconds: int = Field(default=20, ge=5)
    task_dispatch_seconds: int = Field(default=5, ge=1)
    task_max_attempts: int = Field(default=3, ge=1, le=10)
    log_level: str = "INFO"

    @field_validator("log_level")
    @classmethod
    def valid_log_level(cls, value: str) -> str:
        value = value.upper()
        if value not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("unsupported logging level")
        return value

    @model_validator(mode="after")
    def validate_runtime(self) -> "Settings":
        if self.task_heartbeat_seconds * 3 > self.task_lease_seconds:
            raise ValueError("task_lease_seconds must cover at least three heartbeats")
        backend = Path(__file__).resolve().parents[2]
        for name in ("paper_storage_dir", "chroma_data_dir"):
            value = getattr(self, name)
            if not value.is_absolute():
                setattr(self, name, (backend / value).resolve())
        return self

    @property
    def database_url(self) -> str:
        return URL.create(
            "postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        ).render_as_string(hide_password=False)

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
