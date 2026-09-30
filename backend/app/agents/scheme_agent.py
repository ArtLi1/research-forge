import json
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import AgentRun, CandidateScheme, CandidateVersion
from app.providers.chat import ChatModelProvider, OpenAICompatibleChatProvider, load_prompt
from app.schemas.scheme import (
    CandidateSchemeContent,
    CandidateSet,
    RetrievalPlan,
    SchemeGenerateRequest,
    SchemeValidationResult,
)
from app.services.scheme_validation import (
    SchemeValidator,
    build_risk_assessment,
)
from app.services.tasks import TaskService

from .scheme_state import RetrievedKnowledgeItem, SchemeAgentState
from .scheme_tools import SchemeAgentTools, build_default_scheme_tools

MAX_GENERATION_RETRIES = 1
MAX_KNOWLEDGE_PER_TYPE = 15


class SchemeAgent:
    prompt_version = "generate_schemes_v1+offloading_research_guidance_v1"

    def __init__(
        self,
        session: AsyncSession,
        project_id: uuid.UUID,
        request: SchemeGenerateRequest,
        task_id: uuid.UUID,
        *,
        chat: ChatModelProvider | None = None,
        tools: SchemeAgentTools | None = None,
        validator: SchemeValidator | None = None,
    ) -> None:
        self.session = session
        self.project_id = project_id
        self.request = request
        self.task_id = task_id
        self.chat = chat or OpenAICompatibleChatProvider()
        self.tools = tools or build_default_scheme_tools(session)
        self.validator = validator or SchemeValidator(self.chat)
        self.thread_id = str(uuid.uuid4())
        self.trace_steps: list[dict[str, Any]] = []

    async def run(self) -> list[uuid.UUID]:
        run = AgentRun(
            project_id=self.project_id,
            candidate_id=None,
            thread_id=self.thread_id,
            run_type="scheme_generation",
            status="running",
            input=self.request.model_dump(mode="json"),
            output={},
            model=self.chat.model,
            prompt_version=self.prompt_version,
        )
        self.session.add(run)
        await self.session.commit()
        run_id = run.id
        initial: SchemeAgentState = {
            "project_id": str(self.project_id),
            "agent_run_id": str(run.id),
            "thread_id": self.thread_id,
            "goal": self.request.goal,
            "selected_idea_ids": [str(item) for item in self.request.selected_idea_ids],
            "retry_count": 0,
            "steps": [],
        }
        try:
            state = await self._build_graph().ainvoke(
                initial, config={"configurable": {"thread_id": self.thread_id}}
            )
            candidate_ids = [uuid.UUID(item) for item in state["candidate_ids"]]
            run.status = "succeeded"
            run.output = self._trace_output(state)
            run.finished_at = datetime.now(UTC)
            await self.session.commit()
            return candidate_ids
        except Exception as exc:
            await self.session.rollback()
            stored = await self.session.get(AgentRun, run_id)
            if stored is not None:
                stored.status = "failed"
                stored.error = str(exc)[:4000]
                stored.output = {
                    "goal": self.request.goal,
                    "retry_count": 0,
                    "steps": self.trace_steps,
                }
                stored.finished_at = datetime.now(UTC)
                await self.session.commit()
            raise

    def _build_graph(self) -> Any:
        graph = StateGraph(SchemeAgentState)
        graph.add_node("load_context", self._load_context)
        graph.add_node("understand_goal", self._understand_goal)
        graph.add_node("plan_retrieval", self._plan_retrieval)
        graph.add_node("retrieve_knowledge", self._retrieve_knowledge)
        graph.add_node("generate_candidates", self._generate_candidates)
        graph.add_node("validate_candidates", self._validate_candidates)
        graph.add_node("assess_risks", self._assess_risks)
        graph.add_node("persist_candidates", self._persist_candidates)
        graph.add_edge(START, "load_context")
        graph.add_edge("load_context", "understand_goal")
        graph.add_edge("understand_goal", "plan_retrieval")
        graph.add_edge("plan_retrieval", "retrieve_knowledge")
        graph.add_edge("retrieve_knowledge", "generate_candidates")
        graph.add_edge("generate_candidates", "validate_candidates")
        graph.add_conditional_edges(
            "validate_candidates",
            self._route_after_validation,
            {"retry": "generate_candidates", "continue": "assess_risks"},
        )
        graph.add_edge("assess_risks", "persist_candidates")
        graph.add_edge("persist_candidates", END)
        return graph.compile(checkpointer=InMemorySaver())

    async def _progress(self, stage: str, progress: int, message: str) -> None:
        await TaskService(self.session).update(
            self.task_id, status="running", stage=stage, progress=progress, message=message
        )

    def _step(self, state: SchemeAgentState, name: str, **details: Any) -> list[dict[str, Any]]:
        self.trace_steps = [
            *state.get("steps", []),
            {"name": name, "status": "completed", **details},
        ]
        return self.trace_steps

    async def _load_context(self, state: SchemeAgentState) -> dict[str, Any]:
        await self._progress("loading_context", 8, "Agent Tools 正在读取项目上下文与用户想法")
        selected = [uuid.UUID(item) for item in state["selected_idea_ids"]]
        context = await self.tools.project_context.run(self.project_id)
        ideas = await self.tools.user_ideas.run(self.project_id, selected or None)
        return {
            "project_context": context.model_dump(mode="json"),
            "ideas": [item.model_dump(mode="json") for item in ideas],
            "steps": self._step(state, "load_context", idea_count=len(ideas)),
        }

    async def _understand_goal(self, state: SchemeAgentState) -> dict[str, Any]:
        await self._progress("understanding_goal", 15, "正在识别研究目标与硬约束")
        context = dict(state["project_context"])
        context["requested_goal"] = state["goal"]
        context["hard_constraints"] = {
            "must_follow": state["goal"],
            "exclusions": context.get("exclusions", []),
        }
        return {"project_context": context, "steps": self._step(state, "understand_goal")}

    async def _plan_retrieval(self, state: SchemeAgentState) -> dict[str, Any]:
        await self._progress("planning_retrieval", 23, "正在规划场景与算法知识检索")
        plan = await self.chat.generate_structured(
            [
                {
                    "role": "system",
                    "content": load_prompt(
                        "plan_knowledge_retrieval_v2.md", offloading_guidance=True
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"goal": state["goal"], "project_context": state["project_context"]},
                        ensure_ascii=False,
                    ),
                },
            ],
            RetrievalPlan,
            temperature=0,
        )
        scenario_queries = list(
            dict.fromkeys(query.strip() for query in plan.scenario_queries if query.strip())
        )[:3]
        algorithm_queries = list(
            dict.fromkeys(query.strip() for query in plan.algorithm_queries if query.strip())
        )[:3]
        retrieval_plan = {
            "scenario_queries": scenario_queries,
            "algorithm_queries": algorithm_queries,
        }
        return {
            "retrieval_plan": retrieval_plan,
            "steps": self._step(
                state,
                "plan_retrieval",
                scenario_query_count=len(scenario_queries),
                algorithm_query_count=len(algorithm_queries),
            ),
        }

    async def _retrieve_knowledge(self, state: SchemeAgentState) -> dict[str, Any]:
        await self._progress("retrieving_knowledge", 32, "正在检索项目论文中的场景与算法启发")

        async def retrieve(kind: Literal["scenario", "algorithm"]) -> list[RetrievedKnowledgeItem]:
            unique: dict[str, RetrievedKnowledgeItem] = {}
            for query in state["retrieval_plan"][f"{kind}_queries"]:
                for item in await self.tools.knowledge_search.run(
                    self.project_id, query, kind, limit=MAX_KNOWLEDGE_PER_TYPE
                ):
                    current = unique.get(item.id)
                    if current is None or item.score > current.score:
                        unique[item.id] = item
            return sorted(unique.values(), key=lambda item: item.score, reverse=True)[
                :MAX_KNOWLEDGE_PER_TYPE
            ]

        scenarios = await retrieve("scenario")
        algorithms = await retrieve("algorithm")
        if not scenarios and not algorithms:
            raise AppError(
                "INSUFFICIENT_KNOWLEDGE",
                "项目论文中尚无可用于构思的场景或算法知识，请先提取论文知识卡",
                status_code=409,
            )
        return {
            "scenario_knowledge": [item.model_dump(mode="json") for item in scenarios],
            "algorithm_knowledge": [item.model_dump(mode="json") for item in algorithms],
            "steps": self._step(
                state,
                "retrieve_knowledge",
                scenario_count=len(scenarios),
                algorithm_count=len(algorithms),
            ),
        }

    async def _generate_candidates(self, state: SchemeAgentState) -> dict[str, Any]:
        retry_count = state.get("retry_count", 0)
        if state.get("validation") and not state["validation"]["passed"]:
            retry_count += 1
        await self._progress(
            "generating_candidates",
            42 if retry_count == 0 else 58,
            "正在生成三个候选方案" if retry_count == 0 else "正在根据验证反馈修正候选方案",
        )
        generated = await self.chat.generate_structured(
            [
                {
                    "role": "system",
                    "content": load_prompt("generate_schemes_v1.md", offloading_guidance=True),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "goal": state["goal"],
                            "project_context": state["project_context"],
                            "user_ideas": state["ideas"],
                            "scenario_inspirations": state["scenario_knowledge"],
                            "algorithm_inspirations": state["algorithm_knowledge"],
                            "validation_feedback": state.get("validation_feedback", []),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            CandidateSet,
            temperature=0.4,
        )
        return {
            "candidates": [item.model_dump(mode="json") for item in generated.candidates],
            "retry_count": retry_count,
            "steps": self._step(
                state, "generate_candidates", candidate_count=3, retry=retry_count > 0
            ),
        }

    async def _validate_candidates(self, state: SchemeAgentState) -> dict[str, Any]:
        await self._progress("validating_candidates", 70, "Hybrid Evaluator 正在验证候选方案")
        result = await self.validator.validate(
            candidates=[
                CandidateSchemeContent.model_validate(item) for item in state["candidates"]
            ],
            goal=state["goal"],
            project_context=state["project_context"],
        )
        return {
            "candidates": [item.model_dump(mode="json") for item in result.candidates],
            "validation": result.model_dump(mode="json", exclude={"candidates"}),
            "validation_feedback": result.feedback,
            "steps": self._step(
                state, "validate_candidates", passed=result.passed, issue_count=len(result.feedback)
            ),
        }

    @staticmethod
    def _route_after_validation(state: SchemeAgentState) -> Literal["retry", "continue"]:
        if state["validation"]["passed"]:
            return "continue"
        if state.get("retry_count", 0) < MAX_GENERATION_RETRIES:
            return "retry"
        raise AppError(
            "SCHEME_VALIDATION_FAILED",
            "候选方案在最大修正次数后仍未通过验证",
            status_code=502,
            details={"feedback": state.get("validation_feedback", [])},
        )

    async def _assess_risks(self, state: SchemeAgentState) -> dict[str, Any]:
        await self._progress("assessing_risks", 84, "正在汇总目标、兼容性与创新风险")
        validation = SchemeValidationResult.model_validate(
            {**state["validation"], "candidates": state["candidates"]}
        )
        risks = []
        for index, candidate in enumerate(validation.candidates):
            check = validation.constraint_checks[index]
            risks.append(
                build_risk_assessment(
                    candidate,
                    diversity_passed=validation.diversity_passed,
                    goal_alignment_passed=check.goal_alignment_passed,
                    compatibility_passed=check.compatibility_passed,
                    hard_constraint_violations=check.hard_constraint_violations,
                    compatibility_risks=check.compatibility_risks,
                ).model_dump(mode="json")
            )
        return {"risks": risks, "steps": self._step(state, "assess_risks")}

    async def _persist_candidates(self, state: SchemeAgentState) -> dict[str, Any]:
        await self._progress("persisting_candidates", 93, "正在保存候选方案与 Agent Trace")
        ids: list[str] = []
        for raw, risk in zip(state["candidates"], state["risks"], strict=True):
            content = CandidateSchemeContent.model_validate(raw)
            scheme = CandidateScheme(
                project_id=self.project_id,
                title=content.name,
                status="candidate",
                current_version_id=None,
                langgraph_thread_id=self.thread_id,
            )
            self.session.add(scheme)
            await self.session.flush()
            version = CandidateVersion(
                candidate_id=scheme.id,
                version_number=1,
                parent_version_id=None,
                content=content.model_dump(mode="json"),
                user_instruction=None,
                risk_assessment=risk,
                evidence_ids=[],
                model=self.chat.model,
                prompt_version=self.prompt_version,
            )
            self.session.add(version)
            await self.session.flush()
            scheme.current_version_id = version.id
            ids.append(str(scheme.id))
        await self.session.commit()
        return {
            "candidate_ids": ids,
            "steps": self._step(state, "persist_candidates", candidate_count=len(ids)),
        }

    @staticmethod
    def _trace_output(state: SchemeAgentState) -> dict[str, Any]:
        validation = state.get("validation", {})
        return {
            "goal": state["goal"],
            "retrieval_plan": state.get("retrieval_plan", {}),
            "retrieved_scenario_count": len(state.get("scenario_knowledge", [])),
            "retrieved_algorithm_count": len(state.get("algorithm_knowledge", [])),
            "retrieved_knowledge_ids": [
                item["id"]
                for item in [
                    *state.get("scenario_knowledge", []),
                    *state.get("algorithm_knowledge", []),
                ]
            ],
            "candidate_count": len(state.get("candidate_ids", [])),
            "retry_count": state.get("retry_count", 0),
            "validation": {
                "diversity": bool(validation.get("diversity_passed")),
                "goal_alignment": bool(validation.get("goal_alignment_passed")),
                "constraints": bool(validation.get("constraint_passed")),
                "compatibility": bool(validation.get("compatibility_passed")),
            },
            "steps": state.get("steps", []),
        }
