"""Tests for the scan endpoints."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_list_scans_authenticated(client: AsyncClient, auth_headers):
    resp = await client.get("/api/scan", headers=auth_headers["headers"])
    assert resp.status_code == 200
    assert "scans" in resp.json()


async def test_list_scans_unauthenticated(client: AsyncClient):
    resp = await client.get("/api/scan")
    assert resp.status_code == 401


async def test_get_scan_not_found(client: AsyncClient, auth_headers):
    resp = await client.get("/api/scan/nonexistent-id", headers=auth_headers["headers"])
    assert resp.status_code == 404
