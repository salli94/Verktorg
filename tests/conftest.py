import os
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_verktorg.db"

import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.database import Base, engine
from app.main import app


TEST_DB_PATH = Path("./test_verktorg.db")


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
