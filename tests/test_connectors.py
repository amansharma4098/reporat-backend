"""Tests for the connectors endpoints."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_get_connector_schema(client: AsyncClient):
    resp = await client.get("/api/connectors/schema")
    assert resp.status_code == 200
    schemas = resp.json()["schemas"]
    assert "jira" in schemas
    assert "github_issues" in schemas


async def test_list_connectors_authenticated(client: AsyncClient, auth_headers):
    resp = await client.get("/api/connectors", headers=auth_headers["headers"])
    assert resp.status_code == 200
    connectors = resp.json()["connectors"]
    assert len(connectors) > 0
    assert all("type" in c for c in connectors)
    assert all("configured" in c for c in connectors)


async def test_list_connectors_unauthenticated(client: AsyncClient):
    resp = await client.get("/api/connectors")
    assert resp.status_code == 401
