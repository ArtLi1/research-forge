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
            vectors = await self.embedding.embed_documents(documents)
            chunks, _ = await asyncio.to_thread(self.ensure_collections)
            await self._write(chunks, ids, documents, metadatas, vectors, paper_id=paper_id)
        except Exception as exc:
            raise AppError(
                "VECTOR_INDEX_ERROR",
                "向量索引写入失败",
                status_code=502,
                details={"reason": str(exc)},
            ) from exc

    async def delete_paper_chunks(self, paper_id: str) -> None:
        chunks, _ = await asyncio.to_thread(self.ensure_collections)
        await asyncio.to_thread(chunks.delete, where={"paper_id": paper_id})

    async def _write(
        self,
        collection: Collection,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
        vectors: list[list[float]],
        *,
        paper_id: str | None = None,
    ) -> None:
        old_ids: list[str] = []
        if paper_id is not None:
            previous = await asyncio.to_thread(
                collection.get, where={"paper_id": paper_id}, include=[]
            )
            old_ids = previous["ids"]
        if ids:
            await asyncio.to_thread(
                collection.upsert,
                ids=ids,
                documents=documents,
                embeddings=cast(Embeddings, vectors),
                metadatas=cast(Metadatas, metadatas),
            )
        # Preserve the last usable index if embedding or upsert fails.
        stale = sorted(set(old_ids) - set(ids))
        if stale:
            await asyncio.to_thread(collection.delete, ids=stale)

    async def index_knowledge(
        self,
        *,
        paper_id: str,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        try:
            vectors = await self.embedding.embed_documents(documents) if documents else []
            _, knowledge = await asyncio.to_thread(self.ensure_collections)
            await self._write(knowledge, ids, documents, metadatas, vectors, paper_id=paper_id)
        except Exception as exc:
            raise AppError(
                "VECTOR_INDEX_ERROR",
                "知识向量索引写入失败",
                status_code=502,
                details={"reason": str(exc)},
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
                details={"reason": str(exc)},
            ) from exc

    async def search_knowledge(
        self,
        query: str,
        allowed_paper_ids: Sequence[str],
        top_k: int = 8,
        knowledge_type: str | None = None,
    ) -> dict[str, Any]:
        if not allowed_paper_ids:
            return {
                "ids": [[]],
                "documents": [[]],
                "metadatas": [[]],
                "distances": [[]],
            }
        try:
            vector = await self.embedding.embed_query(query)
            _, knowledge = await asyncio.to_thread(self.ensure_collections)
            clauses: list[dict[str, Any]] = [{"paper_id": {"$in": list(allowed_paper_ids)}}]
            if knowledge_type:
                clauses.append({"knowledge_type": knowledge_type})
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
                details={"reason": str(exc)},
            ) from exc
