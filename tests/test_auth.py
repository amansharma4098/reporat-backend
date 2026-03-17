"""Tests for the auth endpoints."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


# ── Signup ───────────────────────────────────────────────────────────────

async def test_signup_success(client: AsyncClient):
    resp = await client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "Pass1234!",
        "name": "Alice",
        "tenant_name": "Alice Corp",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["user"]["email"] == "alice@example.com"
    assert body["tenant"]["slug"] == "alice-corp"


async def test_signup_duplicate_email(client: AsyncClient):
    payload = {
        "email": "dup@example.com",
        "password": "Pass1234!",
        "name": "Dup",
        "tenant_name": "Dup Org",
    }
    await client.post("/api/auth/signup", json=payload)
    resp = await client.post("/api/auth/signup", json={**payload, "tenant_name": "Other Org"})
    assert resp.status_code == 409


async def test_signup_duplicate_tenant(client: AsyncClient):
    await client.post("/api/auth/signup", json={
        "email": "first@example.com",
        "password": "Pass1234!",
        "name": "First",
        "tenant_name": "Same Tenant",
    })
    resp = await client.post("/api/auth/signup", json={
        "email": "second@example.com",
        "password": "Pass1234!",
        "name": "Second",
        "tenant_name": "Same Tenant",
    })
    assert resp.status_code == 409


# ── Login ────────────────────────────────────────────────────────────────

async def test_login_success(client: AsyncClient):
    await client.post("/api/auth/signup", json={
        "email": "login@example.com",
        "password": "Pass1234!",
        "name": "Login User",
        "tenant_name": "Login Org",
    })
    resp = await client.post("/api/auth/login", json={
        "email": "login@example.com",
        "password": "Pass1234!",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["user"]["email"] == "login@example.com"


async def test_login_wrong_password(client: AsyncClient):
    await client.post("/api/auth/signup", json={
        "email": "wrong@example.com",
        "password": "Pass1234!",
        "name": "Wrong",
        "tenant_name": "Wrong Org",
    })
    resp = await client.post("/api/auth/login", json={
        "email": "wrong@example.com",
        "password": "BadPassword",
    })
    assert resp.status_code == 401


async def test_login_nonexistent_user(client: AsyncClient):
    resp = await client.post("/api/auth/login", json={
        "email": "noone@example.com",
        "password": "Pass1234!",
    })
    assert resp.status_code == 401


# ── Refresh ──────────────────────────────────────────────────────────────

async def test_refresh_token(client: AsyncClient):
    signup = await client.post("/api/auth/signup", json={
        "email": "refresh@example.com",
        "password": "Pass1234!",
        "name": "Refresh",
        "tenant_name": "Refresh Org",
    })
    refresh_token = signup.json()["refresh_token"]

    resp = await client.post("/api/auth/refresh", json={
        "refresh_token": refresh_token,
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()


async def test_refresh_invalid_token(client: AsyncClient):
    resp = await client.post("/api/auth/refresh", json={
        "refresh_token": "garbage.token.here",
    })
    assert resp.status_code == 401


# ── Me ───────────────────────────────────────────────────────────────────

async def test_me_authenticated(client: AsyncClient, auth_headers):
    resp = await client.get("/api/auth/me", headers=auth_headers["headers"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "test@example.com"
    assert len(body["tenants"]) == 1
    assert body["tenants"][0]["role"] == "owner"


async def test_me_no_token(client: AsyncClient):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


# ── Invite ───────────────────────────────────────────────────────────────

async def test_invite_user(client: AsyncClient, auth_headers):
    # Create a second user first
    await client.post("/api/auth/signup", json={
        "email": "invitee@example.com",
        "password": "Pass1234!",
        "name": "Invitee",
        "tenant_name": "Invitee Solo Org",
    })
    resp = await client.post(
        "/api/auth/invite",
        json={"email": "invitee@example.com", "role": "member"},
        headers=auth_headers["headers"],
    )
    assert resp.status_code == 200
    assert "invitee@example.com" in resp.json()["message"]


async def test_invite_nonexistent_user(client: AsyncClient, auth_headers):
    resp = await client.post(
        "/api/auth/invite",
        json={"email": "ghost@example.com", "role": "member"},
        headers=auth_headers["headers"],
    )
    assert resp.status_code == 404


async def test_invite_invalid_role(client: AsyncClient, auth_headers):
    await client.post("/api/auth/signup", json={
        "email": "badrole@example.com",
        "password": "Pass1234!",
        "name": "BadRole",
        "tenant_name": "BadRole Org",
    })
    resp = await client.post(
        "/api/auth/invite",
        json={"email": "badrole@example.com", "role": "superadmin"},
        headers=auth_headers["headers"],
    )
    assert resp.status_code == 400
