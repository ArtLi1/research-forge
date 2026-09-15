import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Paper, Project, ProjectPaper


class ProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> list[Project]:
        result = await self.session.scalars(select(Project).order_by(Project.updated_at.desc()))
        return list(result)

    async def get(self, project_id: uuid.UUID) -> Project | None:
        return await self.session.get(Project, project_id)

    async def add(self, project: Project) -> Project:
        self.session.add(project)
        await self.session.flush()
        return project

    async def delete(self, project: Project) -> None:
        await self.session.delete(project)

    async def add_paper(self, association: ProjectPaper) -> ProjectPaper:
        self.session.add(association)
        await self.session.flush()
        return association

    async def has_paper(self, project_id: uuid.UUID, paper_id: uuid.UUID) -> bool:
        return (
            await self.session.get(ProjectPaper, {"project_id": project_id, "paper_id": paper_id})
            is not None
        )

    async def remove_paper(self, project_id: uuid.UUID, paper_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            delete(ProjectPaper).where(
                ProjectPaper.project_id == project_id,
                ProjectPaper.paper_id == paper_id,
            )
        )
        return bool(getattr(result, "rowcount", 0))

    async def list_papers(self, project_id: uuid.UUID) -> list[Paper]:
        result = await self.session.scalars(
            select(Paper)
            .join(ProjectPaper, ProjectPaper.paper_id == Paper.id)
            .where(ProjectPaper.project_id == project_id)
            .order_by(ProjectPaper.added_at.desc())
        )
        return list(result)
