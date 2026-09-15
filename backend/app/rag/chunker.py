from dataclasses import dataclass

import tiktoken

from app.schemas.paper import ChunkData, ParsedDocument


@dataclass(slots=True)
class _Piece:
    text: str
    page: int
    block_type: str


class DomainAwareChunker:
    def __init__(self, target_tokens: int = 900, max_tokens: int = 1200, overlap: int = 120):
        self.target_tokens = target_tokens
        self.max_tokens = max_tokens
        self.overlap = overlap
        self.encoding = tiktoken.get_encoding("cl100k_base")

    def token_count(self, text: str) -> int:
        return len(self.encoding.encode(text))

    def chunk(self, document: ParsedDocument) -> list[ChunkData]:
        chunks: list[ChunkData] = []
        section_title: str | None = None
        section_level: int | None = None
        buffer: list[_Piece] = []

        def flush() -> None:
            nonlocal buffer
            if not buffer:
                return
            content = "\n\n".join(piece.text for piece in buffer).strip()
            chunks.append(
                ChunkData(
                    section_title=section_title,
                    section_level=section_level,
                    chunk_type=self._chunk_type(buffer),
                    content=content,
                    page_start=min(piece.page for piece in buffer),
                    page_end=max(piece.page for piece in buffer),
                    order_index=len(chunks),
                    token_count=self.token_count(content),
                )
            )
            overlap_pieces: list[_Piece] = []
            overlap_tokens = 0
            for piece in reversed(buffer):
                piece_tokens = self.token_count(piece.text)
                if overlap_tokens + piece_tokens > self.overlap:
                    break
                overlap_pieces.insert(0, piece)
                overlap_tokens += piece_tokens
            buffer = overlap_pieces

        for block in document.blocks:
            if block.block_type == "heading":
                flush()
                buffer = []
                section_title = block.content
                section_level = block.heading_level or 1
                continue
            if block.block_type in {"table", "caption", "reference"}:
                flush()
                buffer = []
                single = _Piece(block.content, block.page, block.block_type)
                buffer.append(single)
                flush()
                buffer = []
                continue
            piece = _Piece(block.content, block.page, block.block_type)
            projected = "\n\n".join([*(item.text for item in buffer), piece.text])
            if buffer and self.token_count(projected) > self.target_tokens:
                flush()
                projected = "\n\n".join([*(item.text for item in buffer), piece.text])
            if self.token_count(piece.text) > self.max_tokens:
                flush()
                buffer = []
                self._split_long_piece(piece, chunks, section_title, section_level)
            else:
                buffer.append(piece)
        flush()
        return [chunk for chunk in chunks if chunk.content]

    def _split_long_piece(
        self,
        piece: _Piece,
        chunks: list[ChunkData],
        section_title: str | None,
        section_level: int | None,
    ) -> None:
        tokens = self.encoding.encode(piece.text)
        step = self.max_tokens - self.overlap
        for start in range(0, len(tokens), step):
            part = tokens[start : start + self.max_tokens]
            text = self.encoding.decode(part)
            chunks.append(
                ChunkData(
                    section_title=section_title,
                    section_level=section_level,
                    chunk_type=piece.block_type,
                    content=text,
                    page_start=piece.page,
                    page_end=piece.page,
                    order_index=len(chunks),
                    token_count=len(part),
                )
            )
            if start + self.max_tokens >= len(tokens):
                break

    @staticmethod
    def _chunk_type(pieces: list[_Piece]) -> str:
        types = {piece.block_type for piece in pieces}
        return next(iter(types)) if len(types) == 1 else "body"
