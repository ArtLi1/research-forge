import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.errors import AppError
from app.providers.chroma import ChromaVectorStore
from app.rag.retrieval import KnowledgeRetriever, RetrievalScope, vector_rows
from app.schemas.paper import SearchRequest
from app.services import search


class Collection:
    def __init__(self, fail=False):
        self.rows = {"old": "paper", "unrelated": "other"}
        self.fail = fail
        self.operations = []

    def get(self, *, where, include):
        assert include == []
        return {"ids": [key for key, paper in self.rows.items() if paper == where["paper_id"]]}

    def upsert(self, *, ids, documents, embeddings, metadatas):
        assert len(ids) == len(documents) == len(embeddings) == len(metadatas)
        if self.fail:
            raise RuntimeError("write failed")
        self.operations.append("upsert")
        self.rows.update(zip(ids, [item["paper_id"] for item in metadatas], strict=True))

    def delete(self, *, ids):
        self.operations.append("delete")
        for item in ids:
            del self.rows[item]


def store_with_collection(collection):
    embedding = SimpleNamespace(embed_documents=AsyncMock(return_value=[[0.1, 0.2]]))
    store = ChromaVectorStore(embedding=embedding)
    store.__dict__["_collections"] = (collection, collection)
    return store


@pytest.mark.parametrize("kind", ["chunks", "knowledge"])
async def test_replace_writes_before_cleanup_and_preserves_other_papers(kind):
    collection = Collection()
    store = store_with_collection(collection)
    await getattr(store, f"index_{kind}")(
        paper_id="paper",
        ids=["new"],
        documents=["MEC offloading"],
        metadatas=[{"paper_id": "paper"}],
    )
    assert collection.operations == ["upsert", "delete"]
    assert collection.rows == {"new": "paper", "unrelated": "other"}


@pytest.mark.parametrize("failure", ["embedding", "upsert"])
async def test_failed_reindex_keeps_previous_knowledge(failure):
    collection = Collection(fail=failure == "upsert")
    store = store_with_collection(collection)
    if failure == "embedding":
        store.embedding.embed_documents.side_effect = RuntimeError("model unavailable")
    with pytest.raises(AppError) as error:
        await store.index_knowledge(
            paper_id="paper",
            ids=["new"],
            documents=["MEC offloading"],
            metadatas=[{"paper_id": "paper"}],
        )
    assert error.value.code == "VECTOR_INDEX_ERROR"
    assert collection.rows == {"old": "paper", "unrelated": "other"}


async def test_empty_project_does_not_require_vector_service(monkeypatch):
    session = AsyncMock()
    session.scalars.return_value = []

    def unreachable():
        raise AssertionError("Empty scope must not initialize Chroma")

    monkeypatch.setattr(search, "ChromaVectorStore", unreachable)
    result = await search.SearchService(session).search(SearchRequest(query="MEC"))
    assert not result.items
    assert result.missing_information


async def test_empty_scope_and_versions_skip_remote_search():
    vectors = SimpleNamespace(search_knowledge=AsyncMock(return_value={}))
    retriever = KnowledgeRetriever(vectors)
    await retriever.search(RetrievalScope(), "MEC", "scenario", limit=5)
    await retriever.search(
        RetrievalScope(paper_ids=[str(uuid.uuid4())]), "DAG", "algorithm", limit=5
    )
    vectors.search_knowledge.assert_not_awaited()


async def test_snapshot_cleanup_does_not_delete_later_generation():
    collection = Collection()
    store = store_with_collection(collection)
    previous = await store.paper_vector_ids("paper")
    collection.rows["later-generation"] = "paper"
    await store.delete_vectors(previous)
    assert collection.rows == {"later-generation": "paper", "unrelated": "other"}


def test_inconsistent_vector_rows_fail_closed():
    with pytest.raises(AppError):
        vector_rows(
            {"ids": [["1"]], "documents": [["body"]], "metadatas": [[]], "distances": [[0.1]]}
        )


async def test_batch_failure_keeps_previous_active_vectors():
    collection = Collection()
    store = store_with_collection(collection)
    calls = []

    async def embed(documents):
        calls.append(len(documents))
        if len(calls) == 2:
            raise RuntimeError("second batch failed")
        return [[0.1, 0.2] for _ in documents]

    store.embedding.embed_documents.side_effect = embed
    with pytest.raises(AppError):
        await store.index_chunks(
            paper_id="paper",
            ids=[str(index) for index in range(150)],
            documents=["DAG"] * 150,
            metadatas=[{"paper_id": "paper"}] * 150,
        )
    assert calls == [128, 22]
    assert collection.rows["old"] == "paper"
    assert "delete" not in collection.operations
