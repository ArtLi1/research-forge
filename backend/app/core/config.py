from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ResearchForge"
    app_env: str = "development"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    frontend_origin: str = "http://localhost:5173"

    postgres_host: str = "192.168.220.129"
    postgres_port: int = 5432
    postgres_user: str = "postgres"
    postgres_password: str = Field(repr=False)
    postgres_db: str = "agent"

    redis_host: str = "192.168.220.129"
    redis_port: int = 6379
    redis_db: int = 0

    chroma_host: str = "127.0.0.1"
    chroma_port: int = 8001
    chroma_data_dir: Path = Path(r"D:\data\chroma")
    chroma_index_version: str = "1"

    paper_storage_dir: Path = Path("data/papers")
    max_upload_mb: int = 50
    max_upload_files: int = 20

    llm_base_url: str | None = None
    llm_api_key: str | None = Field(default=None, repr=False)
    llm_model: str | None = None
    llm_extraction_model: str | None = None
    llm_timeout_seconds: int = 300
    llm_max_retries: int = 2

    @property
    def database_url(self) -> str:
        password = quote_plus(self.postgres_password)
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
