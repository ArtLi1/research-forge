import asyncio

from fastapi import APIRouter
from redis.asyncio import Redis
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import engine
from app.providers.chroma import ChromaVectorStore
from app.providers.embedding import ChromaDefaultEmbeddingProvider
from app.schemas.common import HealthResponse, ServiceHealth, SystemSettingsRead

router = APIRouter(tags=["health"])


@router.get("/settings", response_model=SystemSettingsRead)
async def system_settings() -> SystemSettingsRead:
    settings = get_settings()
    return SystemSettingsRead(
        app_name=settings.app_name,
        llm_base_url=settings.llm_base_url,
        llm_model=settings.llm_model,
        llm_api_key_configured=bool(settings.llm_api_key),
        embedding_provider=ChromaDefaultEmbeddingProvider.provider,
        embedding_model=ChromaDefaultEmbeddingProvider.model,
        chroma_endpoint=f"http://{settings.chroma_host}:{settings.chroma_port}",
        chroma_data_dir=str(settings.chroma_data_dir),
        third_party_notice="知识提取、比较、构思和评估会把相关论文内容发送到所配置的第三方模型服务。",
    )


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()

    async def check_postgres() -> ServiceHealth:
        async def probe() -> None:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))

        try:
            await asyncio.wait_for(probe(), timeout=3)
            return ServiceHealth(status="healthy")
        except Exception as exc:
            return ServiceHealth(status="unhealthy", detail=str(exc))

    async def check_redis() -> ServiceHealth:
        client = Redis.from_url(settings.redis_url)
        try:
            await asyncio.wait_for(client.ping(), timeout=3)
            return ServiceHealth(status="healthy")
        except Exception as exc:
            return ServiceHealth(status="unhealthy", detail=str(exc))
        finally:
            await client.aclose()

    async def check_chroma() -> ServiceHealth:
        try:
            await asyncio.wait_for(asyncio.to_thread(ChromaVectorStore().heartbeat), timeout=3)
            return ServiceHealth(status="healthy")
        except Exception as exc:
            return ServiceHealth(status="unhealthy", detail=str(exc))

    postgres, redis, chroma = await asyncio.gather(check_postgres(), check_redis(), check_chroma())
    services = {
        "application": ServiceHealth(status="healthy"),
        "postgres": postgres,
        "redis": redis,
        "chroma": chroma,
    }
    overall = (
        "healthy"
        if all(service.status == "healthy" for service in services.values())
        else "degraded"
    )
    return HealthResponse(status=overall, services=services)
