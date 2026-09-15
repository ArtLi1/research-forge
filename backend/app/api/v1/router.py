from fastapi import APIRouter

from app.api.v1 import comparison, health, ideas, metadata, papers, projects, schemes, search, tasks

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(projects.router)
api_router.include_router(comparison.router)
api_router.include_router(papers.router)
api_router.include_router(search.router)
api_router.include_router(tasks.router)
api_router.include_router(metadata.router)
api_router.include_router(ideas.router)
api_router.include_router(schemes.router)
