import uuid
from types import SimpleNamespace

import pytest

from app.providers import chat
from app.rag.knowledge import KnowledgeExtractor, merge_knowledge, stage_knowledge
from app.schemas.knowledge import AlgorithmKnowledge, PaperKnowledgeContent, ScenarioKnowledge


def test_chat_provider_accepts_extraction_model_override(monkeypatch) -> None:
    settings = SimpleNamespace(
        llm_base_url="https://example.test",
        llm_api_key="secret",
        llm_model="deepseek-v4-pro",
        llm_timeout_seconds=300,
        llm_max_retries=2,
        llm_output_tokens=8192,
    )
    monkeypatch.setattr(chat, "get_settings", lambda: settings)
    monkeypatch.setattr(chat, "AsyncOpenAI", lambda **_: object())

    provider = chat.OpenAICompatibleChatProvider(model="deepseek-v4-flash")

    assert provider.model == "deepseek-v4-flash"


def test_merge_knowledge_deduplicates_by_name_and_keeps_more_complete_item() -> None:
    merged = merge_knowledge(
        [
            PaperKnowledgeContent(
                scenarios=[
                    ScenarioKnowledge(
                        name="Edge inference",
                        description="Devices offload inference.",
                        key_challenge="Latency",
                    )
                ]
            ),
            PaperKnowledgeContent(
                scenarios=[
                    ScenarioKnowledge(
                        name="  edge INFERENCE ",
                        description="Devices offload time-sensitive inference to edge servers.",
                        key_challenge="Joint latency and energy control",
                        innovation_point="Adaptive split points",
                    )
                ],
                algorithms=[
                    AlgorithmKnowledge(
                        name="Actor critic",
                        core_idea="Learn sequential decisions.",
                        key_mechanism="Policy and value networks",
                        innovation_point="Constraint-aware updates",
                    )
                ],
            ),
        ]
    )

    assert len(merged.scenarios) == 1
    assert merged.scenarios[0].innovation_point == "Adaptive split points"
    assert [item.name for item in merged.algorithms] == ["Actor critic"]


@pytest.mark.asyncio
async def test_knowledge_index_creates_one_typed_vector_per_item(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class VectorStore:
        async def index_knowledge(self, **values) -> None:
            captured.update(values)

    paper_id, version_id = uuid.uuid4(), uuid.uuid4()
    content = PaperKnowledgeContent(
        scenarios=[
            ScenarioKnowledge(
                name="Mobile edge inference",
                description="Mobile devices execute split inference.",
                key_challenge="Changing bandwidth",
            )
        ],
        algorithms=[
            AlgorithmKnowledge(
                name="Adaptive partitioning",
                core_idea="Select the split online.",
                key_mechanism="State-aware partition decisions",
                innovation_point="Joint communication awareness",
            )
        ],
    )

    await stage_knowledge(VectorStore(), paper_id, version_id, content)

    assert captured["ids"] == [
        f"{version_id}:scenario:0",
        f"{version_id}:algorithm:0",
    ]
    assert [item["knowledge_type"] for item in captured["metadatas"]] == [  # type: ignore[index]
        "scenario",
        "algorithm",
    ]
    assert "Challenge:" in captured["documents"][0]  # type: ignore[index]
    assert "Mechanism:" in captured["documents"][1]  # type: ignore[index]
    assert captured["replace"] is False


def test_large_tables_and_body_respect_extraction_budget():
    extractor = KnowledgeExtractor(SimpleNamespace(), max_chars=1000)
    contents = ["table" * 1100, "body" * 750]
    batches = extractor.batches(contents)
    assert max(map(len, batches)) <= 1000
    assert "".join(batches).replace("\n\n", "") == "".join(contents)
