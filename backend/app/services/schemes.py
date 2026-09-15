import json
import uuid
from datetime import UTC, datetime
from typing import Any

from redis import Redis
from rq import Queue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.scheme_tools import build_default_scheme_tools
from app.core.config import get_settings
from app.core.errors import AppError, not_found
from app.models import (
    AgentRun,
    BackgroundTask,
    CandidateScheme,
    CandidateVersion,
    Project,
    UserIdea,
)
from app.providers.chat import ChatModelProvider, OpenAICompatibleChatProvider, load_prompt
from app.schemas.scheme import (
    AgentTraceRead,
    CandidateConstraintCheck,
    CandidateSchemeContent,
    CandidateSchemeDetail,
    CandidateSchemeSummary,
    CandidateVersionRead,
    SchemeAbandonRequest,
    SchemeAcceptRequest,
    SchemeGenerateRequest,
    SchemeReviseRequest,
    SchemeRiskAssessment,
)
from app.services.project_knowledge import ProjectKnowledgeService
from app.services.scheme_validation import (
    build_risk_assessment,
)


class SchemeService:
    revision_prompt_version = "revise_scheme_v1"

    def __init__(self, session: AsyncSession, *, chat: ChatModelProvider | None = None) -> None:
        self.session = session
        self.chat = chat

    async def start_generation(
        self, project_id: uuid.UUID, request: SchemeGenerateRequest
    ) -> BackgroundTask:
        if await self.session.get(Project, project_id) is None:
            raise not_found("project", project_id)
        if request.selected_idea_ids:
            count = len(
                list(
                    await self.session.scalars(
                        select(UserIdea.id).where(
                            UserIdea.project_id == project_id,
                            UserIdea.id.in_(request.selected_idea_ids),
                        )
                    )
                )
            )
            if count != len(set(request.selected_idea_ids)):
                raise AppError(
                    "IDEA_NOT_FOUND",
                    "存在不属于当前项目的用户想法",
                    status_code=404,
                )
        task = BackgroundTask(
            task_type="scheme_generate",
            resource_type="project",
            resource_id=project_id,
            payload=request.model_dump(mode="json"),
        )
        self.session.add(task)
        await self.session.commit()
        await self._enqueue(task)
        return task

    async def list(self, project_id: uuid.UUID) -> list[CandidateSchemeSummary]:
        if await self.session.get(Project, project_id) is None:
            raise not_found("project", project_id)
        schemes = list(
            await self.session.scalars(
                select(CandidateScheme)
                .where(CandidateScheme.project_id == project_id)
                .order_by(CandidateScheme.created_at.desc())
            )
        )
        return [await self._summary(item) for item in schemes]

    async def get(self, scheme_id: uuid.UUID) -> CandidateSchemeDetail:
        scheme = await self.session.get(CandidateScheme, scheme_id)
        if scheme is None:
            raise not_found("scheme", scheme_id)
        versions = list(
            await self.session.scalars(
                select(CandidateVersion)
                .where(CandidateVersion.candidate_id == scheme.id)
                .order_by(CandidateVersion.version_number.desc())
            )
        )
        summary = await self._summary(scheme)
        return CandidateSchemeDetail(
            **summary.model_dump(),
            versions=[self._version_read(item) for item in versions],
        )

    async def revise(
        self, scheme_id: uuid.UUID, request: SchemeReviseRequest
    ) -> CandidateSchemeDetail:
        scheme = await self.session.get(CandidateScheme, scheme_id)
        if scheme is None:
            raise not_found("scheme", scheme_id)
        if scheme.status != "candidate":
            raise AppError(
                "SCHEME_NOT_CANDIDATE",
                "只有候选状态的方案可以修改",
                status_code=409,
            )
        current = await self._current_version(scheme)
        self._check_version(current, request.expected_version_id)
        context = await self._revision_context(scheme.project_id, request.instruction)
        await self.session.commit()
        provider = self.chat or OpenAICompatibleChatProvider()
        revised = await provider.generate_structured(
            [
                {
                    "role": "system",
                    "content": load_prompt("revise_scheme_v1.md"),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "project_context": context,
                            "current_scheme": current.content,
                            "current_risk_assessment": current.risk_assessment,
                            "user_instruction": request.instruction,
                            "scenario_inspirations": context["scenario_knowledge"],
                            "algorithm_inspirations": context["algorithm_knowledge"],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            CandidateSchemeContent,
            temperature=0.2,
        )
        constraint = await provider.generate_structured(
            [
                {
                    "role": "system",
                    "content": load_prompt("check_single_scheme_constraints_v1.md"),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "goal": context["project"]["research_goal"],
                            "exclusions": context["project"]["exclusions"],
                            "candidate": revised.model_dump(mode="json"),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            CandidateConstraintCheck,
            temperature=0,
        )
        previous_risk = SchemeRiskAssessment.model_validate(current.risk_assessment)
        risk = build_risk_assessment(
            revised,
            diversity_passed=previous_risk.diversity_passed,
            goal_alignment_passed=constraint.goal_alignment_passed,
            compatibility_passed=constraint.compatibility_passed,
            hard_constraint_violations=constraint.hard_constraint_violations,
            compatibility_risks=constraint.compatibility_risks,
        )
        scheme = await self._locked_candidate(scheme_id)
        current = await self._current_version(scheme)
        self._check_version(current, request.expected_version_id)
        version = CandidateVersion(
            candidate_id=scheme.id,
            version_number=current.version_number + 1,
            parent_version_id=current.id,
            content=revised.model_dump(mode="json"),
            user_instruction=request.instruction,
            risk_assessment=risk.model_dump(mode="json"),
            evidence_ids=[],
            model=provider.model,
            prompt_version=self.revision_prompt_version,
        )
        self.session.add(version)
        await self.session.flush()
        scheme.title = revised.name
        scheme.current_version_id = version.id
        self.session.add(
            AgentRun(
                project_id=scheme.project_id,
                candidate_id=scheme.id,
                thread_id=scheme.langgraph_thread_id,
                run_type="scheme_revision",
                status="succeeded",
                input=request.model_dump(mode="json"),
                output={"version_id": str(version.id), "version_number": version.version_number},
                model=provider.model,
                prompt_version=self.revision_prompt_version,
                finished_at=datetime.now(UTC),
            )
        )
        await self.session.commit()
        await self.session.refresh(scheme)
        return await self.get(scheme.id)

    async def accept(
        self, scheme_id: uuid.UUID, request: SchemeAcceptRequest
    ) -> CandidateSchemeDetail:
        scheme = await self.session.scalar(
            select(CandidateScheme).where(CandidateScheme.id == scheme_id).with_for_update()
        )
        if scheme is None:
            raise not_found("scheme", scheme_id)
        current = await self._current_version(scheme)
        if scheme.status == "accepted":
            return await self.get(scheme.id)
        if scheme.status != "candidate":
            raise AppError(
                "SCHEME_NOT_CANDIDATE",
                "只有候选状态的方案可以接受",
                status_code=409,
            )
        self._check_version(current, request.expected_version_id)
        risk = SchemeRiskAssessment.model_validate(current.risk_assessment)
        if risk.hard_constraint_violations:
            raise AppError(
                "SCHEME_HARD_CONSTRAINT_FAILED",
                "方案仍违反项目硬约束，请先修改",
                status_code=409,
                details={"violations": risk.hard_constraint_violations},
            )
        generation_run = await self.session.scalar(
            select(AgentRun)
            .where(
                AgentRun.thread_id == scheme.langgraph_thread_id,
                AgentRun.run_type == "scheme_generation",
            )
            .order_by(AgentRun.started_at)
        )
        idea_ids = {
            uuid.UUID(item)
            for item in (
                generation_run.input.get("selected_idea_ids", []) if generation_run else []
            )
        }
        await ProjectKnowledgeService(self.session).add_confirmed_scheme(
            scheme.project_id,
            scheme.id,
            CandidateSchemeContent.model_validate(current.content),
            risk,
            idea_ids=idea_ids,
        )
        scheme.status = "accepted"
        scheme.accepted_at = datetime.now(UTC)
        self.session.add(
            AgentRun(
                project_id=scheme.project_id,
                candidate_id=scheme.id,
                thread_id=scheme.langgraph_thread_id,
                run_type="scheme_acceptance",
                status="succeeded",
                input=request.model_dump(mode="json"),
                output={
                    "accepted_version_id": str(current.id),
                    "project_knowledge_category": "confirmed_schemes",
                },
                model=current.model,
                prompt_version=current.prompt_version,
                finished_at=datetime.now(UTC),
            )
        )
        await self.session.commit()
        await self.session.refresh(scheme)
        return await self.get(scheme.id)

    async def abandon(
        self, scheme_id: uuid.UUID, request: SchemeAbandonRequest
    ) -> CandidateSchemeDetail:
        scheme = await self._locked_candidate(scheme_id)
        current = await self._current_version(scheme)
        scheme.status = "abandoned"
        scheme.abandoned_reason = request.reason
        self.session.add(
            AgentRun(
                project_id=scheme.project_id,
                candidate_id=scheme.id,
                thread_id=scheme.langgraph_thread_id,
                run_type="scheme_abandonment",
                status="succeeded",
                input=request.model_dump(mode="json"),
                output={"abandoned_version_id": str(current.id)},
                model=current.model,
                prompt_version=current.prompt_version,
                finished_at=datetime.now(UTC),
            )
        )
        await self.session.commit()
        await self.session.refresh(scheme)
        return await self.get(scheme.id)

    async def get_agent_trace(self, scheme_id: uuid.UUID) -> AgentTraceRead:
        scheme = await self.session.get(CandidateScheme, scheme_id)
        if scheme is None:
            raise not_found("scheme", scheme_id)
        run = await self.session.scalar(
            select(AgentRun)
            .where(
                AgentRun.thread_id == scheme.langgraph_thread_id,
                AgentRun.run_type == "scheme_generation",
            )
            .order_by(AgentRun.started_at.desc())
        )
        if run is None:
            raise not_found("agent_run", scheme_id)
        output = run.output or {}
        return AgentTraceRead(
            run_id=run.id,
            status=run.status,
            goal=str(output.get("goal") or run.input.get("goal") or ""),
            retrieval_plan=dict(output.get("retrieval_plan", {})),
            retrieved_scenario_count=int(output.get("retrieved_scenario_count", 0)),
            retrieved_algorithm_count=int(output.get("retrieved_algorithm_count", 0)),
            retrieved_knowledge_ids=list(output.get("retrieved_knowledge_ids", [])),
            candidate_count=int(output.get("candidate_count", 0)),
            retry_count=int(output.get("retry_count", 0)),
            validation=dict(output.get("validation", {})),
            steps=list(output.get("steps", [])),
        )

    async def _locked_candidate(self, scheme_id: uuid.UUID) -> CandidateScheme:
        scheme = await self.session.scalar(
            select(CandidateScheme).where(CandidateScheme.id == scheme_id).with_for_update()
        )
        if scheme is None:
            raise not_found("scheme", scheme_id)
        if scheme.status != "candidate":
            raise AppError(
                "SCHEME_NOT_CANDIDATE",
                "只有候选状态的方案可以修改或放弃",
                status_code=409,
            )
        return scheme

    async def _current_version(self, scheme: CandidateScheme) -> CandidateVersion:
        if scheme.current_version_id is None:
            raise AppError("SCHEME_VERSION_CONFLICT", "候选方案没有当前版本", status_code=409)
        version = await self.session.get(CandidateVersion, scheme.current_version_id)
        if version is None:
            raise AppError("SCHEME_VERSION_CONFLICT", "候选方案当前版本不存在", status_code=409)
        return version

    @staticmethod
    def _check_version(version: CandidateVersion, expected_version_id: uuid.UUID) -> None:
        if version.id != expected_version_id:
            raise AppError(
                "SCHEME_VERSION_CONFLICT",
                "方案版本已变化，请刷新后重试",
                status_code=409,
                details={"current_version_id": str(version.id)},
            )

    async def _revision_context(
        self, project_id: uuid.UUID, query: str
    ) -> dict[str, Any]:
        tools = build_default_scheme_tools(self.session)
        project = await tools.project_context.run(project_id)
        scenarios = await tools.knowledge_search.run(project_id, query, "scenario", limit=10)
        algorithms = await tools.knowledge_search.run(project_id, query, "algorithm", limit=10)
        return {
            "project": project.model_dump(mode="json"),
            "scenario_knowledge": [item.model_dump(mode="json") for item in scenarios],
            "algorithm_knowledge": [item.model_dump(mode="json") for item in algorithms],
        }

    async def _summary(self, scheme: CandidateScheme) -> CandidateSchemeSummary:
        version = await self._current_version(scheme)
        return CandidateSchemeSummary(
            id=scheme.id,
            project_id=scheme.project_id,
            title=scheme.title,
            status=scheme.status,
            current_version_id=version.id,
            langgraph_thread_id=scheme.langgraph_thread_id,
            abandoned_reason=scheme.abandoned_reason,
            accepted_at=scheme.accepted_at,
            current_version=self._version_read(version),
            created_at=scheme.created_at,
            updated_at=scheme.updated_at,
        )

    @staticmethod
    def _version_read(version: CandidateVersion) -> CandidateVersionRead:
        return CandidateVersionRead(
            id=version.id,
            candidate_id=version.candidate_id,
            version_number=version.version_number,
            parent_version_id=version.parent_version_id,
            content=CandidateSchemeContent.model_validate(version.content),
            user_instruction=version.user_instruction,
            risk_assessment=SchemeRiskAssessment.model_validate(version.risk_assessment),
            model=version.model,
            prompt_version=version.prompt_version,
            created_at=version.created_at,
        )

    async def _enqueue(self, task: BackgroundTask) -> None:
        settings = get_settings()
        try:
            queue = Queue(
                "scheme_generate",
                connection=Redis.from_url(settings.redis_url),
                default_timeout=3600,
            )
            job = queue.enqueue(
                "app.tasks.scheme_generation.generate_schemes_job",
                str(task.resource_id),
                str(task.id),
                task.payload,
                job_timeout=3600,
            )
            task.rq_job_id = job.id
            await self.session.commit()
        except Exception as exc:
            task.status = "failed"
            task.stage = "enqueue_failed"
            task.message = "候选方案任务提交失败"
            task.error = str(exc)
            await self.session.commit()
            raise AppError(
                "TASK_QUEUE_ERROR",
                "候选方案任务提交失败",
                status_code=502,
                details={"reason": str(exc)},
            ) from exc
