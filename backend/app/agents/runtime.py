import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.agents.context import ResearchContextService
from app.agents.state import ResearchState
from app.agents.workflow import ResearchWorkflow
from app.core.config import get_settings
from app.models import AgentRun, CandidateScheme, CandidateVersion
from app.prompts import get_prompt
from app.providers.chat import OpenAICompatibleChatProvider
from app.rag.retrieval import KnowledgeRetriever
from app.schemas.scheme import SchemeGenerateRequest
from app.services.scheme_validation import build_risk_assessment
from app.services.tasks import TaskService
from app.tasks.context import TaskContext
from app.tasks.types import TaskStatus


async def generate_research(context: TaskContext) -> None:
    settings = get_settings()
    request = SchemeGenerateRequest.model_validate(context.payload)
    chat = OpenAICompatibleChatProvider()
    prompt = get_prompt("generate_schemes_v1.md", offloading=True)
    async with context.transaction() as (session, _):
        run = await session.scalar(select(AgentRun).where(AgentRun.task_id == context.task_id))
        if run is None:
            state = await ResearchContextService(session).load(
                context.resource_id,
                request.goal,
                request.selected_idea_ids,
            )
            run = AgentRun(
                id=uuid.uuid4(),
                task_id=context.task_id,
                project_id=context.resource_id,
                thread_id=str(context.task_id),
                run_type="scheme_generation",
                status="running",
                input=request.model_dump(mode="json"),
                output={},
                model=chat.model,
                prompt_version=prompt.version,
                checkpoint=state.model_dump(mode="json"),
            )
            session.add(run)
        else:
            state = ResearchState.model_validate(run.checkpoint)
            run.status, run.error = "running", None
        run_id = run.id

    async def checkpoint(current: ResearchState) -> None:
        progress = {"retrieve": 23, "propose": 35, "evaluate": 60, "done": 85}[current.next_step]
        async with context.transaction() as (session, task):
            stored = await session.get(AgentRun, run_id)
            if stored is None:
                raise RuntimeError("Research run disappeared")
            stored.checkpoint = current.model_dump(mode="json")
            stored.output = current.trace()
            task.stage = current.next_step
            task.progress = max(task.progress, progress)
            messages = {
                "plan_retrieval": "检索计划已完成",
                "retrieve_knowledge": "研究知识已检索",
                "generate_candidates": "候选方案已生成",
                "validate_candidates": "方案校验已完成",
            }
            task.message = messages[current.steps[-1].name]

    workflow = ResearchWorkflow(
        chat,
        KnowledgeRetriever(concurrency=settings.rag_concurrency),
        max_revisions=settings.agent_max_revisions,
        top_k=settings.rag_top_k,
        checkpoint=checkpoint,
    )
    result = await workflow.run(state)
    if result.validation is None or not result.validation.passed:
        raise RuntimeError("Unvalidated research result")
    async with context.transaction() as (session, task):
        stored = await session.get(AgentRun, run_id)
        if stored is None:
            raise RuntimeError("Research run disappeared")
        scheme_ids = []
        checks = {item.candidate_index: item for item in result.validation.constraint_checks}
        for index, content in enumerate(result.candidates):
            check = checks[index]
            risk = build_risk_assessment(
                content,
                diversity_passed=result.validation.diversity_passed,
                goal_alignment_passed=check.goal_alignment_passed,
                compatibility_passed=check.compatibility_passed,
                hard_constraint_violations=check.hard_constraint_violations,
                compatibility_risks=check.compatibility_risks,
            )
            scheme_id, version_id = uuid.uuid4(), uuid.uuid4()
            session.add(
                CandidateScheme(
                    id=scheme_id,
                    project_id=context.resource_id,
                    title=content.name,
                    status="candidate",
                    current_version_id=version_id,
                    langgraph_thread_id=stored.thread_id,
                )
            )
            await session.flush()
            session.add(
                CandidateVersion(
                    id=version_id,
                    candidate_id=scheme_id,
                    version_number=1,
                    content=content.model_dump(mode="json"),
                    risk_assessment=risk.model_dump(mode="json"),
                    evidence_ids=[],
                    model=chat.model,
                    prompt_version=prompt.version,
                )
            )
            scheme_ids.append(str(scheme_id))
        stored.status, stored.finished_at = "succeeded", datetime.now(UTC)
        stored.checkpoint = result.model_dump(mode="json")
        stored.output = {
            **result.trace(candidate_count=len(scheme_ids)),
            "candidate_ids": scheme_ids,
        }
        TaskService.finish(task, TaskStatus.SUCCEEDED, f"已生成 {len(scheme_ids)} 个候选研究方案")
