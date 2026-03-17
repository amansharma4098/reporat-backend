"""Shared fixtures for tests — uses an in-memory SQLite database."""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# Must patch database BEFORE importing the app
import app.core.database as _db_mod

_test_engine = create_async_engine("sqlite+aiosqlite:///", echo=False)
_test_session_factory = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)

# Monkey-patch the module-level objects so the app uses our test DB
_db_mod.engine = _test_engine
_db_mod.async_session = _test_session_factory


async def _override_get_db():
    async with _test_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()

_db_mod.get_db = _override_get_db

# NOW import the app (after patching)
from main import app  # noqa: E402
from app.core.database import Base  # noqa: E402
from app.core import db_models  # noqa: E402, F401  — registers models


@pytest_asyncio.fixture(autouse=True)
async def _setup_db():
    """Create all tables before each test, drop after."""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient):
    """Sign up a user and return auth headers + metadata."""
    resp = await client.post("/api/auth/signup", json={
        "email": "test@example.com",
        "password": "StrongP@ss1",
        "name": "Test User",
        "tenant_name": "Test Org",
    })
    data = resp.json()
    token = data["access_token"]
    return {
        "headers": {"Authorization": f"Bearer {token}"},
        "user": data["user"],
        "tenant": data["tenant"],
        "access_token": token,
        "refresh_token": data["refresh_token"],
    }
