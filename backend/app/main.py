import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import configure_logging
from app.db.session import Database
from app.tasks.dispatcher import dispatcher_loop

logger = structlog.get_logger()


def create_app(*, database: Database | None = None, dispatch_tasks: bool = True) -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.log_level)
        settings.paper_storage_dir.mkdir(parents=True, exist_ok=True)
        runtime_db = database or Database(settings.database_url)
        application.state.database = runtime_db
        dispatcher = (
            asyncio.create_task(dispatcher_loop(runtime_db.sessions), name="task-dispatcher")
            if dispatch_tasks
            else None
        )
        try:
            yield
        finally:
            if dispatcher:
                dispatcher.cancel()
                await asyncio.gather(dispatcher, return_exceptions=True)
            if database is None:
                await runtime_db.close()

    application = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)
    if database is not None:
        application.state.database = database
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    application.include_router(api_router)

    @application.middleware("http")
    async def request_context(request: Request, call_next: Any) -> Any:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        started = perf_counter()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "http_request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=round((perf_counter() - started) * 1000, 2),
            )
            return response
        finally:
            structlog.contextvars.clear_contextvars()

    @application.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.error(
                "application_error", code=exc.code, exc_info=(type(exc), exc, exc.__traceback__)
            )
        return error_response(exc.status_code, exc.code, exc.message, exc.details)

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"loc": list(item["loc"]), "msg": item["msg"], "type": item["type"]}
            for item in exc.errors()
        ]
        return error_response(422, "VALIDATION_ERROR", "请求参数不符合要求", {"errors": errors})

    @application.exception_handler(IntegrityError)
    async def conflict_handler(_: Request, exc: IntegrityError) -> JSONResponse:
        logger.warning("database_conflict", error_type=type(exc).__name__)
        return error_response(409, "DATA_CONFLICT", "数据已变化或存在重复记录，请刷新后重试")

    @application.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unexpected_error",
            error_type=type(exc).__name__,
            request_id=getattr(request.state, "request_id", None),
        )
        response = error_response(500, "INTERNAL_ERROR", "服务内部错误")
        response.headers["X-Request-ID"] = getattr(request.state, "request_id", "")
        return response

    @application.get("/")
    async def root() -> dict[str, Any]:
        return {"name": settings.app_name, "docs": "/docs"}

    return application


def error_response(
    status: int, code: str, message: str, details: dict[str, Any] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details or {}}},
    )


app = create_app()
