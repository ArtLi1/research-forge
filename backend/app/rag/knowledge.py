import re
import uuid
from typing import Any

from app.core.errors import AppError
from app.prompts import get_prompt
from app.providers.chat import ChatModelProvider
from app.providers.chroma import ChromaVectorStore
from app.schemas.knowledge import AlgorithmKnowledge, PaperKnowledgeContent, ScenarioKnowledge


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _merge_items[K: (ScenarioKnowledge, AlgorithmKnowledge)](
    target: dict[str, K], entries: list[K]
) -> None:
    def completeness(row: K) -> int:
        return sum(len(str(value).strip()) for value in row.model_dump().values() if value)

    for item in entries:
        key = normalize_text(item.name)
        previous = target.get(key)
        if previous is None or completeness(item) > completeness(previous):
            target[key] = item.model_copy(deep=True)


def merge_knowledge(parts: list[PaperKnowledgeContent]) -> PaperKnowledgeContent:
    scenarios: dict[str, ScenarioKnowledge] = {}
    algorithms: dict[str, AlgorithmKnowledge] = {}
    for part in parts:
        _merge_items(scenarios, part.scenarios)
        _merge_items(algorithms, part.algorithms)
    return PaperKnowledgeContent(
        scenarios=list(scenarios.values()), algorithms=list(algorithms.values())
    )


class KnowledgeExtractor:
    def __init__(self, chat: ChatModelProvider, *, max_chars: int = 14000) -> None:
        self.chat, self.max_chars = chat, max_chars
        self.prompt = get_prompt("extract_paper_knowledge_v1.md")

    def batches(self, contents: list[str]) -> list[str]:
        # Even a large standalone table must respect the model input budget.
        texts = [
            text[start : start + self.max_chars]
            for text in contents
            for start in range(0, len(text), self.max_chars)
        ]
        result, current = [], ""
        for text in texts:
            if current and len(current) + len(text) + 2 > self.max_chars:
                result.append(current)
                current = ""
            current = current + "\n\n" + text if current else text
        if current:
            result.append(current)
        return result

    async def extract(self, title: str, contents: list[str]) -> PaperKnowledgeContent:
        parts = []
        for batch in self.batches(contents):
            parts.append(
                await self.chat.generate_structured(
                    [
                        {"role": "system", "content": self.prompt.content},
                        {"role": "user", "content": f"论文：{title}\n\n片段：\n{batch}"},
                    ],
                    PaperKnowledgeContent,
                    temperature=0,
                )
            )
        content = merge_knowledge(parts)
        if not content.scenarios and not content.algorithms:
            raise AppError(
                "KNOWLEDGE_EXTRACTION_FAILED", "未提取到可用的场景或算法知识", status_code=422
            )
        return content


def knowledge_vectors(
    paper_id: uuid.UUID, version_id: uuid.UUID, content: PaperKnowledgeContent
) -> dict[str, Any]:
    ids, documents, metadatas = [], [], []
    groups: list[tuple[str, list[ScenarioKnowledge | AlgorithmKnowledge]]] = [
        ("scenario", list(content.scenarios)),
        ("algorithm", list(content.algorithms)),
    ]
    for kind, entries in groups:
        for index, item in enumerate(entries):
            if isinstance(item, ScenarioKnowledge):
                document = (
                    f"{item.name}\n{item.description}\nChallenge:\n{item.key_challenge}"
                    f"\nInnovation:\n{item.innovation_point or ''}"
                )
            else:
                document = (
                    f"{item.name}\nCore idea:\n{item.core_idea}\nMechanism:\n{item.key_mechanism}"
                    f"\nInnovation:\n{item.innovation_point}"
                )
            ids.append(f"{version_id}:{kind}:{index}")
            documents.append(document)
            metadatas.append(
                {
                    "paper_id": str(paper_id),
                    "knowledge_version_id": str(version_id),
                    "knowledge_type": kind,
                    "item_index": index,
                    "name": item.name,
                }
            )
    return {"ids": ids, "documents": documents, "metadatas": metadatas}


async def stage_knowledge(
    store: ChromaVectorStore,
    paper_id: uuid.UUID,
    version_id: uuid.UUID,
    content: PaperKnowledgeContent,
) -> list[str]:
    vectors = knowledge_vectors(paper_id, version_id, content)
    await store.index_knowledge(paper_id=str(paper_id), replace=False, **vectors)
    return list(vectors["ids"])
