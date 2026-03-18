from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.db_models import TenantMember, User
from app.api.deps import get_current_tenant

router = APIRouter(prefix="/api/team", tags=["team"])


@router.get("/members")
async def list_members(current: dict = Depends(get_current_tenant)):
    """Return all members of the current tenant."""
    db: AsyncSession = current["db"]
    tenant_id = current["tenant_id"]

    result = await db.execute(
        select(TenantMember, User)
        .join(User, TenantMember.user_id == User.id)
        .where(TenantMember.tenant_id == tenant_id)
    )

    members = [
        {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": tm.role,
            "joined_at": tm.joined_at.isoformat() if tm.joined_at else None,
        }
        for tm, user in result.all()
    ]
    return {"members": members}


@router.delete("/members/{user_id}")
async def remove_member(user_id: str, current: dict = Depends(get_current_tenant)):
    """Remove a member from the tenant. Owner only."""
    if current["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can remove members")

    db: AsyncSession = current["db"]
    tenant_id = current["tenant_id"]

    if user_id == current["user"].id:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")

    result = await db.execute(
        select(TenantMember).where(
            TenantMember.tenant_id == tenant_id,
            TenantMember.user_id == user_id,
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=404, detail="Member not found in this tenant")

    await db.delete(membership)
    await db.commit()
    return {"message": "Member removed"}
