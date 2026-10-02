import os
import uuid

import pytest
from sqlalchemy import event, text

os.environ.setdefault("POSTGRES_PASSWORD", "isolated-test-password")

from fakes import MemoryVectors  # noqa: E402

from app import models  # noqa: E402, F401
from app.core.config import get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import Database  # noqa: E402
from app.rag import retrieval  # noqa: E402
from app.services import search, tasks  # noqa: E402
from app.tasks import papers  # noqa: E402


@pytest.fixture
async def database(tmp_path):
    url = os.getenv("TEST_DATABASE_URL")
    schema = f"test_{uuid.uuid4().hex}" if url else None
    db = Database(url or f"sqlite+aiosqlite:///{tmp_path / 'research.db'}", schema=schema)
    if schema:
        async with db.engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    else:

        @event.listens_for(db.engine.sync_engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

    async with db.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield db
    finally:
        if schema:
            async with db.engine.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await db.close()


@pytest.fixture
def adapters(monkeypatch, tmp_path):
    store = MemoryVectors()
    for module in (papers, retrieval, search):
        monkeypatch.setattr(module, "ChromaVectorStore", lambda: store)
    monkeypatch.setattr(
        tasks,
        "_submit_job",
        lambda kind, task_id, generation, existing: existing or f"{task_id}-{generation}",
    )
    monkeypatch.setattr(get_settings(), "paper_storage_dir", tmp_path / "papers")
    return store
