import re
from pathlib import Path
from typing import Any, cast

import pymupdf
import pymupdf4llm

from app.core.errors import AppError
from app.schemas.paper import ParsedBlock, ParsedDocument

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
CAPTION_RE = re.compile(r"^(fig(?:ure)?|table)\s*[.\d:]", re.IGNORECASE)


class PdfParser:
    def parse(self, path: Path) -> ParsedDocument:
        try:
            with pymupdf.open(path) as document:
                if document.page_count == 0:
                    raise ValueError("PDF 没有页面")
                metadata = dict(document.metadata or {})
            pages = cast(
                list[dict[str, Any]],
                pymupdf4llm.to_markdown(
                    path,
                    page_chunks=True,
                    show_progress=False,
                ),
            )
        except Exception as exc:
            raise AppError(
                "PAPER_PARSE_FAILED",
                "PDF 解析失败",
                status_code=422,
                details={"reason": str(exc)},
            ) from exc

        blocks: list[ParsedBlock] = []
        warnings: list[str] = []
        order_index = 0
        for page_index, page in enumerate(pages, start=1):
            page_number = int(page.get("metadata", {}).get("page", page_index - 1)) + 1
            text = str(page.get("text", "")).strip()
            if not text:
                warnings.append(f"第 {page_number} 页没有可提取文本")
                continue
            for raw_block in re.split(r"\n\s*\n", text):
                content = raw_block.strip()
                if not content:
                    continue
                heading = HEADING_RE.match(content)
                block_type = "paragraph"
                heading_level = None
                if heading:
                    block_type = "heading"
                    heading_level = len(heading.group(1))
                    content = heading.group(2).strip()
                elif "|" in content and "\n" in content:
                    block_type = "table"
                elif CAPTION_RE.match(content):
                    block_type = "caption"
                elif content.lower().startswith(("references", "bibliography")):
                    block_type = "reference"
                blocks.append(
                    ParsedBlock(
                        block_type=block_type,
                        content=content,
                        page=page_number,
                        order_index=order_index,
                        heading_level=heading_level,
                    )
                )
                order_index += 1

        if not blocks:
            raise AppError(
                "PAPER_PARSE_FAILED",
                "PDF 没有可提取的文本；MVP 不支持扫描版 PDF",
                status_code=422,
            )
        return ParsedDocument(metadata=metadata, blocks=blocks, warnings=warnings)
