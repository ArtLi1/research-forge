import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, not_found
from app.models import Paper, Project, ProjectPaper
from app.repositories.projects import ProjectRepository
from app.schemas.project import ProjectCreate, ProjectPaperCreate, ProjectUpdate


class ProjectService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ProjectRepository(session)

    async def list_all(self) -> list[Project]:
        return await self.repo.list_all()

    async def get(self, project_id: uuid.UUID) -> Project:
        project = await self.repo.get(project_id)
        if project is None:
            raise not_found("project", project_id)
        return project

    async def create(self, data: ProjectCreate) -> Project:
        project = Project(**data.model_dump())
        await self.repo.add(project)
        await self.session.commit()
        await self.session.refresh(project)
        return project

    async def update(self, project_id: uuid.UUID, data: ProjectUpdate) -> Project:
        project = await self.get(project_id)
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(project, key, value)
        await self.session.commit()
        await self.session.refresh(project)
        return project

    async def delete(self, project_id: uuid.UUID) -> None:
        project = await self.get(project_id)
        await self.repo.delete(project)
        await self.session.commit()

    async def add_paper(
        self, project_id: uuid.UUID, paper_id: uuid.UUID, data: ProjectPaperCreate
    ) -> ProjectPaper:
        await self.get(project_id)
        if await self.session.get(Paper, paper_id) is None:
            raise not_found("paper", paper_id)
        if await self.repo.has_paper(project_id, paper_id):
            raise AppError(
                "DUPLICATE_PROJECT_PAPER",
                "论文已在该项目中",
                status_code=409,
            )
        association = ProjectPaper(
            project_id=project_id,
            paper_id=paper_id,
            **data.model_dump(),
        )
        await self.repo.add_paper(association)
        await self.session.commit()
        return association

    async def remove_paper(self, project_id: uuid.UUID, paper_id: uuid.UUID) -> None:
        await self.get(project_id)
        if not await self.repo.remove_paper(project_id, paper_id):
            raise not_found("paper", paper_id)
        await self.session.commit()

    async def list_papers(self, project_id: uuid.UUID) -> list[Paper]:
        await self.get(project_id)
        return await self.repo.list_papers(project_id)
