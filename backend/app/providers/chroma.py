import asyncio
import os
from collections.abc import Sequence
from functools import cached_property
from typing import Any, cast

import chromadb
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection
from chromadb.api.types import Embeddings, Metadatas, Where

from app.core.config import get_settings
from app.core.errors import AppError
from app.providers.embedding import ChromaDefaultEmbeddingProvider, EmbeddingProvider

PAPER_CHUNKS = "paper_chunks"
PAPER_KNOWLEDGE = "paper_knowledge"


class ChromaVectorStore:
    def __init__(self, embedding: EmbeddingProvider | None = None) -> None:
        settings = get_settings()
        self.host = settings.chroma_host
        self.port = settings.chroma_port
        self.embedding = embedding or ChromaDefaultEmbeddingProvider()
        self.index_version = settings.chroma_index_version

    @cached_property
    def client(self) -> ClientAPI:
        local_hosts = "127.0.0.1,localhost"
        os.environ["NO_PROXY"] = ",".join(
            dict.fromkeys(
                part.strip()
                for part in f"{os.environ.get('NO_PROXY', '')},{local_hosts}".split(",")
                if part.strip()
            )
        )
        os.environ["no_proxy"] = os.environ["NO_PROXY"]
        return chromadb.HttpClient(host=self.host, port=self.port)

    def heartbeat(self) -> int:
        return self.client.heartbeat()

    def ensure_collections(self) -> tuple[Collection, Collection]:
        return self._collections

    @cached_property
    def _collections(self) -> tuple[Collection, Collection]:
        metadata = {
            "embedding_provider": "chroma-default",
            "embedding_model": "all-MiniLM-L6-v2",
            "embedding_dimension": 384,
            "index_version": self.index_version,
            "hnsw:space": "cosine",
        }
        chunks = self.client.get_or_create_collection(PAPER_CHUNKS, metadata=metadata)
        knowledge = self.client.get_or_create_collection(PAPER_KNOWLEDGE, metadata=metadata)
        for collection in (chunks, knowledge):
            actual = collection.metadata or {}
            for key in ("embedding_model", "embedding_dimension", "index_version", "hnsw:space"):
                if key in actual and actual[key] != metadata[key]:
                    raise AppError(
                        "VECTOR_CONFIG_ERROR", "向量集合配置与当前模型不一致", status_code=503
                    )
        return chunks, knowledge

    async def index_chunks(
        self,
        *,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
        paper_id: str | None = None,
    ) -> None:
        if not ids:
            return
        try:
            chunks, _ = await asyncio.to_thread(self.ensure_collections)
            await self._index(chunks, ids, documents, metadatas, paper_id=paper_id)
        except Exception as exc:
            raise AppError(
                "VECTOR_INDEX_ERROR",
                "向量索引写入失败",
                status_code=502,
            ) from exc

    async def delete_paper_chunks(self, paper_id: str) -> None:
        chunks, _ = await asyncio.to_thread(self.ensure_collections)
        await asyncio.to_thread(chunks.delete, where={"paper_id": paper_id})

    async def paper_vector_ids(self, paper_id: str, *, knowledge: bool = False) -> list[str]:
        collections = await asyncio.to_thread(self.ensure_collections)
        collection = collections[1 if knowledge else 0]
        previous = await asyncio.to_thread(collection.get, where={"paper_id": paper_id}, include=[])
        return list(previous["ids"])

    async def delete_vectors(self, ids: list[str], *, knowledge: bool = False) -> None:
        if ids:
            collections = await asyncio.to_thread(self.ensure_collections)
            await asyncio.to_thread(collections[1 if knowledge else 0].delete, ids=ids)

    async def _write(
        self,
        collection: Collection,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
        vectors: list[list[float]],
    ) -> None:
        if ids:
            await asyncio.to_thread(
                collection.upsert,
                ids=ids,
                documents=documents,
                embeddings=cast(Embeddings, vectors),
                metadatas=cast(Metadatas, metadatas),
            )

    async def _index(
        self,
        collection: Collection,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
        *,
        paper_id: str | None,
    ) -> None:
        if not len(ids) == len(documents) == len(metadatas) or len(set(ids)) != len(ids):
            raise ValueError("Vector records must have matching lengths and unique IDs")
        previous_ids: list[str] = []
        if paper_id:
            previous = await asyncio.to_thread(
                collection.get, where={"paper_id": paper_id}, include=[]
            )
            previous_ids = list(previous["ids"])
        for start in range(0, len(ids), 128):
            end = start + 128
            vectors = await self.embedding.embed_documents(documents[start:end])
            if len(vectors) != len(ids[start:end]):
                raise ValueError("Embedding count does not match documents")
            await self._write(
                collection, ids[start:end], documents[start:end], metadatas[start:end], vectors
            )
        stale = sorted(set(previous_ids) - set(ids))
        if stale:
            await asyncio.to_thread(collection.delete, ids=stale)

    async def index_knowledge(
        self,
        *,
        paper_id: str,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
        replace: bool = True,
    ) -> None:
        try:
            _, knowledge = await asyncio.to_thread(self.ensure_collections)
            await self._index(
                knowledge, ids, documents, metadatas, paper_id=paper_id if replace else None
            )

        except Exception as exc:
            raise AppError(
                "VECTOR_INDEX_ERROR",
                "知识向量索引写入失败",
                status_code=502,
            ) from exc

    async def search_chunks(
        self,
        query: str,
        allowed_paper_ids: Sequence[str],
        top_k: int,
        chunk_types: list[str],
    ) -> dict[str, Any]:
        if not allowed_paper_ids:
            return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
        try:
            vector = await self.embedding.embed_query(query)
            chunks, _ = await asyncio.to_thread(self.ensure_collections)
            clauses: list[dict[str, Any]] = [{"paper_id": {"$in": list(allowed_paper_ids)}}]
            if chunk_types:
                clauses.append({"chunk_type": {"$in": chunk_types}})
            where = clauses[0] if len(clauses) == 1 else {"$and": clauses}
            result = await asyncio.to_thread(
                chunks.query,
                query_embeddings=cast(Embeddings, [vector]),
                n_results=top_k,
                where=cast(Where, where),
                include=["documents", "metadatas", "distances"],
            )
            return dict(result)
        except Exception as exc:
            raise AppError(
                "VECTOR_INDEX_ERROR",
                "向量检索失败",
                status_code=502,
            ) from exc

    async def search_knowledge(
        self,
        query: str,
        allowed_paper_ids: Sequence[str],
        top_k: int = 8,
        knowledge_type: str | None = None,
        *,
        version_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        if not allowed_paper_ids:
            return {
                "ids": [[]],
                "documents": [[]],
                "metadatas": [[]],
                "distances": [[]],
            }
        if version_ids is not None and not version_ids:
            return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
        try:
            vector = await self.embedding.embed_query(query)
            _, knowledge = await asyncio.to_thread(self.ensure_collections)
            clauses: list[dict[str, Any]] = [{"paper_id": {"$in": list(allowed_paper_ids)}}]
            if knowledge_type:
                clauses.append({"knowledge_type": knowledge_type})
            if version_ids is not None:
                clauses.append({"knowledge_version_id": {"$in": version_ids}})
            where = clauses[0] if len(clauses) == 1 else {"$and": clauses}
            result = await asyncio.to_thread(
                knowledge.query,
                query_embeddings=cast(Embeddings, [vector]),
                n_results=top_k,
                where=cast(Where, where),
                include=["documents", "metadatas", "distances"],
            )
            return dict(result)
        except Exception as exc:
            raise AppError(
                "VECTOR_INDEX_ERROR",
                "知识向量检索失败",
                status_code=502,
            ) from exc
