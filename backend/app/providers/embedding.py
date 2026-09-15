from typing import Protocol

from chromadb.utils.embedding_functions import DefaultEmbeddingFunction


class EmbeddingProvider(Protocol):
    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


class ChromaDefaultEmbeddingProvider:
    provider = "chroma-default"
    model = "all-MiniLM-L6-v2"
    dimension = 384

    def __init__(self) -> None:
        self._function = DefaultEmbeddingFunction()

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        import asyncio

        vectors = await asyncio.to_thread(self._function, texts)
        return [[float(value) for value in vector] for vector in vectors]

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed_documents([text]))[0]
