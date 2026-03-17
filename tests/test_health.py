"""Tests for root and health endpoints."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_root(client: AsyncClient):
    resp = await client.get("/")
    assert resp.status_code == 200
    assert resp.json()["name"] == "RepoRat"


async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
