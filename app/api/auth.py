import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.db_models import User, Tenant, TenantMember
from app.core.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token,
)
from app.api.deps import get_current_user, get_current_tenant

router = APIRouter(prefix="/api/auth", tags=["auth"])


# --- Request / Response Schemas ---

class SignupRequest(BaseModel):
    email: str
    password: str
    name: str
    tenant_name: str


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class InviteRequest(BaseModel):
    email: str
    role: str = "member"


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


# --- Helpers ---

def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# --- Endpoints ---

@router.post("/signup")
async def signup(req: SignupRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == req.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="An account with this email already exists. Please sign in.")

    slug = _slugify(req.tenant_name)
    existing_tenant = await db.execute(select(Tenant).where(Tenant.slug == slug))
    if existing_tenant.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Tenant name already taken")

    user = User(email=req.email, name=req.name, password_hash=hash_password(req.password))
    db.add(user)
    await db.flush()

    tenant = Tenant(name=req.tenant_name, slug=slug, owner_id=user.id)
    db.add(tenant)
    await db.flush()

    membership = TenantMember(tenant_id=tenant.id, user_id=user.id, role="owner")
    db.add(membership)
    await db.commit()

    token_data = {"sub": user.id, "tenant_id": tenant.id, "role": "owner"}
    return {
        "access_token": create_access_token(token_data),
        "refresh_token": create_refresh_token(token_data),
        "token_type": "bearer",
        "user": {"id": user.id, "email": user.email, "name": user.name},
        "tenant": {"id": tenant.id, "name": tenant.name, "slug": tenant.slug},
    }


@router.post("/login")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == req.email.lower()))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User does not exist. Please sign up first.")
    if not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect password. Please try again.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    member_result = await db.execute(
        select(TenantMember).where(TenantMember.user_id == user.id)
    )
    membership = member_result.scalars().first()
    if not membership:
        raise HTTPException(status_code=403, detail="User has no tenant membership")

    # Get tenant info
    tenant_result = await db.execute(select(Tenant).where(Tenant.id == membership.tenant_id))
    tenant = tenant_result.scalar_one_or_none()

    token_data = {"sub": user.id, "tenant_id": membership.tenant_id, "role": membership.role}
    return {
        "access_token": create_access_token(token_data),
        "refresh_token": create_refresh_token(token_data),
        "token_type": "bearer",
        "user": {"id": user.id, "email": user.email, "name": user.name},
        "tenant": {"id": tenant.id, "name": tenant.name, "slug": tenant.slug} if tenant else None,
    }


@router.post("/refresh")
async def refresh(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token(req.refresh_token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Not a refresh token")

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    token_data = {
        "sub": user.id,
        "tenant_id": payload.get("tenant_id"),
        "role": payload.get("role"),
    }
    return {
        "access_token": create_access_token(token_data),
        "refresh_token": create_refresh_token(token_data),
        "token_type": "bearer",
    }


@router.get("/me")
async def get_me(current: dict = Depends(get_current_user)):
    user = current["user"]
    db = current["db"]

    memberships_result = await db.execute(
        select(TenantMember, Tenant)
        .join(Tenant, TenantMember.tenant_id == Tenant.id)
        .where(TenantMember.user_id == user.id)
    )
    tenants = [
        {
            "tenant_id": tm.tenant_id,
            "tenant_name": t.name,
            "slug": t.slug,
            "role": tm.role,
        }
        for tm, t in memberships_result.all()
    ]

    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "tenants": tenants,
    }


@router.post("/invite")
async def invite_user(req: InviteRequest, current: dict = Depends(get_current_tenant)):
    if current["role"] not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can invite users")

    db = current["db"]
    tenant_id = current["tenant_id"]

    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found. They must sign up first.")

    existing = await db.execute(
        select(TenantMember).where(
            TenantMember.tenant_id == tenant_id,
            TenantMember.user_id == user.id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="User is already a member of this tenant")

    if req.role not in ("admin", "member"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'member'")

    membership = TenantMember(tenant_id=tenant_id, user_id=user.id, role=req.role)
    db.add(membership)
    await db.commit()

    return {"message": f"Invited {req.email} as {req.role}", "user_id": user.id}
