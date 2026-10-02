import asyncio
import uuid
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from starlette.datastructures import Headers

from app.core.config import Settings
from app.core.errors import AppError
from app.models import BackgroundTask, Paper
from app.providers import chat
from app.providers.storage import LocalPaperStorage
from app.services.papers import PaperService


@pytest.mark.parametrize("truncated", [False, True])
async def test_model_client_always_closes_and_truncation_is_rejected(monkeypatch, truncated):
    client = MagicMock()
    client.__aenter__.return_value = client
    client.chat.completions.create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="length" if truncated else "stop",
                    message=SimpleNamespace(content='{"value": "MEC"}'),
                )
            ]
        )
    )
    monkeypatch.setattr(chat, "AsyncOpenAI", lambda **_: client)
    monkeypatch.setattr(
        chat,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            postgres_password="test",
            llm_base_url="https://test.invalid",
            llm_api_key="test-key",
            llm_model="test-model",
        ),
    )
    provider = chat.OpenAICompatibleChatProvider()
    if truncated:
        with pytest.raises(AppError) as error:
            await provider.generate_text([{"role": "user", "content": "MEC"}])
        assert error.value.details == {}
    else:
        assert await provider.generate_text([{"role": "user", "content": "MEC"}])
    client.__aexit__.assert_awaited_once()


async def test_structured_repair_is_bounded_and_preserves_input_messages(monkeypatch):
    class Result(BaseModel):
        count: int

    monkeypatch.setattr(
        chat,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            postgres_password="test",
            llm_base_url="https://test.invalid",
            llm_api_key="test-key",
            llm_model="test-model",
        ),
    )
    provider = chat.OpenAICompatibleChatProvider()
    provider.generate_text = AsyncMock(side_effect=['{"count": "bad"}', '{"count": 3}'])
    messages = [{"role": "user", "content": "Research data"}]
    result = await provider.generate_structured(messages, Result)
    assert result.count == 3
    assert messages == [{"role": "user", "content": "Research data"}]
    assert provider.generate_text.await_count == 2
    provider.generate_text = AsyncMock(return_value="invalid output")
    with pytest.raises(AppError):
        await provider.generate_structured(messages, Result)
    assert provider.generate_text.await_count == 2


async def test_cancelled_upload_removes_partial_file(tmp_path):
    class Upload:
        filename, content_type = "research.pdf", "application/pdf"
        closed = False
        calls = 0

        async def read(self, _):
            self.calls += 1
            if self.calls == 1:
                return b"%PDF-1.7 partial content"
            raise asyncio.CancelledError()

        async def close(self):
            self.closed = True

    upload = Upload()
    with pytest.raises(asyncio.CancelledError):
        await LocalPaperStorage(tmp_path).save(upload, uuid.uuid4())
    assert upload.closed
    assert not list(tmp_path.glob("*.pdf"))


async def test_lost_commit_acknowledgement_preserves_owned_file(database, adapters, monkeypatch):
    async with database.sessions() as session:
        commit = session.commit
        calls = 0

        async def lose_acknowledgement():
            nonlocal calls
            calls += 1
            await commit()
            if calls == 2:
                raise ConnectionError("commit acknowledgement lost")

        monkeypatch.setattr(session, "commit", lose_acknowledgement)
        upload = UploadFile(
            BytesIO(b"%PDF-1.7 test"),
            filename="research.pdf",
            headers=Headers({"content-type": "application/pdf"}),
        )
        with pytest.raises(ConnectionError, match="acknowledgement lost"):
            await PaperService(session).upload([upload], None)
    async with database.sessions() as session:
        paper = await session.scalar(select(Paper))
        from pathlib import Path

        assert paper and Path(paper.file_path).exists()
        assert await session.scalar(select(func.count()).select_from(BackgroundTask)) == 1
