from typing import Any

from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = {}


class ErrorResponse(BaseModel):
    error: ErrorBody


class ServiceHealth(BaseModel):
    status: str
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str
    services: dict[str, ServiceHealth]


class SystemSettingsRead(BaseModel):
    app_name: str
    llm_base_url: str | None
    llm_model: str | None
    llm_api_key_configured: bool
    embedding_provider: str
    embedding_model: str
    chroma_endpoint: str
    chroma_data_dir: str
    third_party_notice: str
