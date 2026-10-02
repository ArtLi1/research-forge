import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pymupdf
import pytest
from fakes import FakeChatProvider, checks, diverse_candidates, knowledge, research_task
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.agents import runtime
from app.main import create_app
from app.models import (
    AgentRun,
    BackgroundTask,
    CandidateScheme,
    CandidateVersion,
    Paper,
    PaperChunk,
    PaperKnowledgeCard,
    PaperKnowledgeVersion,
)
from app.rag.retrieval import KnowledgeRetriever, RetrievalScope
from app.schemas.scheme import RetrievalPlan
from app.tasks import papers
from app.tasks.dispatcher import dispatch_once
from app.tasks.runner import run_task


def pdf_bytes():
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), "Computation Offloading", fontsize=20)
        page.insert_text((72, 110), "Mobile devices execute DAG tasks with edge servers.")
        page.insert_text((72, 140), "Queue-aware scheduling reduces latency and energy.")
        document.set_metadata({"title": "Computation Offloading"})
        return document.tobytes()


async def test_original_api_paper_to_research_to_human_memory(database, adapters, monkeypatch):
    chat = FakeChatProvider(
        [
            knowledge(),
            RetrievalPlan(scenario_queries=["MEC DAG"], algorithm_queries=["queue scheduling"]),
            diverse_candidates(),
            checks(),
        ]
    )
    monkeypatch.setattr(papers, "OpenAICompatibleChatProvider", lambda **_: chat)
    monkeypatch.setattr(runtime, "OpenAICompatibleChatProvider", lambda: chat)
    app = create_app(database=database, dispatch_tasks=False)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        response = await client.post(
            "/api/v1/projects",
            json={
                "name": "卸载研究",
                "research_goal": "降低 DAG 卸载时延",
                "exclusions": ["不得使用云端执行"],
            },
        )
        assert response.status_code == 201, response.text
        project_id = response.json()["id"]
        empty = await client.post(
            f"/api/v1/projects/{project_id}/schemes/generate",
            json={"goal": "降低 DAG 计算卸载时延"},
        )
        assert empty.status_code == 409
        response = await client.post(
            "/api/v1/papers/upload",
            data={"project_id": project_id},
            files={"files": ("offloading.pdf", pdf_bytes(), "application/pdf")},
        )
        assert response.status_code == 202, response.text
        uploaded = response.json()[0]
        paper_id, task_id = uploaded["paper"]["id"], uuid.UUID(uploaded["task_id"])
        conflict = await client.post(f"/api/v1/papers/{paper_id}/reparse")
        assert conflict.status_code == 409
        await run_task(database, task_id, 1)
        response = await client.get(f"/api/v1/tasks/{task_id}")
        assert response.json()["status"] == "queued"
        assert response.json()["task_type"] == "knowledge_extract"
        await dispatch_once(database.sessions)
        await run_task(database, task_id, 2)
        ready = await client.get(f"/api/v1/papers/{paper_id}/knowledge")
        assert ready.status_code == 200, ready.text
        assert ready.json()["content"]["algorithms"][0]["name"] == "DAG scheduler"
        assert (await client.get(f"/api/v1/tasks/{task_id}/events")).text.startswith(
            "event: completed\n"
        )
        # Staged/abandoned vector generations must never appear as evidence.
        adapters.chunks["uncommitted"] = ("STALE CHUNK", {"paper_id": paper_id})
        result = await client.post(
            "/api/v1/search",
            json={"query": "DAG scheduling", "scope": "project", "project_id": project_id},
        )
        assert result.status_code == 200, result.text
        assert all(item["content"] != "STALE CHUNK" for item in result.json()["items"])
        generated = await client.post(
            f"/api/v1/projects/{project_id}/schemes/generate",
            json={"goal": "降低 DAG 计算卸载时延，不得使用云端执行"},
        )
        assert generated.status_code == 202, generated.text
        generation_id = uuid.UUID(generated.json()["id"])
        await run_task(database, generation_id, 1)
        await run_task(database, generation_id, 1)  # At-least-once queue delivery.
        response = await client.get(f"/api/v1/projects/{project_id}/schemes")
        assert response.status_code == 200, response.text
        schemes = response.json()
        assert len(schemes) == 3
        scheme = schemes[0]
        trace = await client.get(f"/api/v1/schemes/{scheme['id']}/agent-run")
        assert trace.json()["candidate_count"] == 3
        assert all(trace.json()["validation"].values())
        memory_before = await client.get(f"/api/v1/projects/{project_id}/knowledge")
        assert memory_before.json() == []  # Only the user accepts research conclusions.
        accepted = await client.post(
            f"/api/v1/schemes/{scheme['id']}/accept",
            json={"expected_version_id": scheme["current_version_id"]},
        )
        assert accepted.status_code == 200, accepted.text
        memory = await client.get(f"/api/v1/projects/{project_id}/knowledge")
        assert memory.json()[0]["category"] == "confirmed_schemes"
    async with database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(PaperKnowledgeVersion)) == 1
        assert await session.scalar(select(func.count()).select_from(CandidateScheme)) == 3
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AgentRun)
                .where(AgentRun.run_type == "scheme_generation")
            )
            == 1
        )


async def test_worker_crash_resumes_database_checkpoint(database, adapters, monkeypatch):
    task = await research_task(database, adapters)
    reached_proposal = asyncio.Event()

    class InterruptedChat(FakeChatProvider):
        async def generate_structured(self, messages, response_model, **kwargs):
            if response_model.__name__ == "CandidateSet":
                reached_proposal.set()
                await asyncio.Event().wait()
            return await super().generate_structured(messages, response_model, **kwargs)

    first = InterruptedChat([RetrievalPlan(scenario_queries=["MEC"], algorithm_queries=["DAG"])])
    monkeypatch.setattr(runtime, "OpenAICompatibleChatProvider", lambda: first)
    worker = asyncio.create_task(run_task(database, task.id, 1))
    await asyncio.wait_for(reached_proposal.wait(), timeout=10)
    worker.cancel()
    with pytest.raises(asyncio.CancelledError):
        await worker
    async with database.transaction() as session:
        row = await session.get(BackgroundTask, task.id)
        row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        stored = await session.scalar(select(AgentRun).where(AgentRun.task_id == task.id))
        assert stored.checkpoint["next_step"] == "propose"
    await dispatch_once(database.sessions)
    second = FakeChatProvider([diverse_candidates(), checks()])
    monkeypatch.setattr(runtime, "OpenAICompatibleChatProvider", lambda: second)
    await run_task(database, task.id, 2)
    async with database.sessions() as session:
        stored = await session.scalar(select(AgentRun).where(AgentRun.task_id == task.id))
        assert stored.status == "succeeded"
        assert stored.output["candidate_count"] == 3
        assert await session.scalar(select(func.count()).select_from(AgentRun)) == 1
    assert len(second.messages) == 2


async def test_candidate_persistence_failure_rolls_back_whole_batch(
    database, adapters, monkeypatch
):
    task = await research_task(database, adapters)
    chat = FakeChatProvider(
        [
            RetrievalPlan(scenario_queries=["MEC"], algorithm_queries=["DAG"]),
            diverse_candidates(),
            checks(),
        ]
    )
    monkeypatch.setattr(runtime, "OpenAICompatibleChatProvider", lambda: chat)

    def reject_versions(session, *_):
        if any(isinstance(value, CandidateVersion) for value in session.new):
            raise RuntimeError("persistence interrupted")

    event.listen(Session, "before_flush", reject_versions)
    try:
        with pytest.raises(RuntimeError, match="persistence interrupted"):
            await run_task(database, task.id, 1)
    finally:
        event.remove(Session, "before_flush", reject_versions)
    async with database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(CandidateScheme)) == 0
        assert await session.scalar(select(func.count()).select_from(CandidateVersion)) == 0
        row = await session.get(BackgroundTask, task.id)
        assert row.status == "failed"
        run = await session.scalar(select(AgentRun).where(AgentRun.task_id == task.id))
        assert run.status == "failed" and run.checkpoint["next_step"] == "done"


async def test_reextraction_keeps_committed_history_for_inflight_snapshots(
    database, adapters, monkeypatch
):
    await research_task(database, adapters)
    async with database.transaction() as session:
        paper = await session.scalar(select(Paper))
        card = await session.scalar(select(PaperKnowledgeCard))
        old_version = str(card.current_version_id)
        paper_id = paper.id
        session.add(
            PaperChunk(
                paper_id=paper_id,
                chunk_type="text",
                content="DAG edge scheduling",
                page_start=1,
                page_end=1,
                order_index=0,
                token_count=5,
                chroma_id=str(uuid.uuid4()),
            )
        )
        task = BackgroundTask(
            task_type="knowledge_extract",
            resource_type="paper",
            resource_id=paper_id,
            dispatch_count=1,
        )
        session.add(task)
    chat = FakeChatProvider([knowledge()])
    monkeypatch.setattr(papers, "OpenAICompatibleChatProvider", lambda **_: chat)
    await run_task(database, task.id, 1)
    async with database.sessions() as session:
        card = await session.scalar(select(PaperKnowledgeCard))
        current_version = str(card.current_version_id)
    assert old_version != current_version
    retriever = KnowledgeRetriever(adapters)
    for version in (old_version, current_version):
        rows = await retriever.search(
            RetrievalScope(paper_ids=[str(paper_id)], knowledge_version_ids=[version]),
            "DAG",
            "algorithm",
            limit=5,
        )
        assert len(rows) == 1 and rows[0].id.startswith(version + ":")
