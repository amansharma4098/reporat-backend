from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.db_models import User, Tenant, TenantMember
from app.core.security import decode_token

_bearer_scheme = HTTPBearer()


async def _extract_token(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> str:
    return credentials.credentials


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(_extract_token),
) -> dict:
    try:
        payload = decode_token(token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id = payload.get("sub")
    tenant_id = payload.get("tenant_id")
    role = payload.get("role")

    result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return {"user": user, "tenant_id": tenant_id, "role": role, "db": db}


async def get_current_tenant(current: dict = Depends(get_current_user)) -> dict:
    if not current["tenant_id"]:
        raise HTTPException(status_code=400, detail="No tenant context in token")
    db = current["db"]
    result = await db.execute(select(Tenant).where(Tenant.id == current["tenant_id"]))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    current["tenant"] = tenant
    return current
