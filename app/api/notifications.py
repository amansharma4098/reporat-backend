from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.db_models import NotificationConfig
from app.api.deps import get_current_tenant
from app.services.notifications import send_notification

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class NotificationConfigRequest(BaseModel):
    type: str  # slack, discord
    webhook_url: str
    enabled: bool = True
    notify_on: str = "all"  # all, failed, critical_only


@router.post("/config")
async def save_notification_config(req: NotificationConfigRequest, current: dict = Depends(get_current_tenant)):
    if req.type not in ("slack", "discord"):
        raise HTTPException(status_code=400, detail="Type must be 'slack' or 'discord'")
    if req.notify_on not in ("all", "failed", "critical_only"):
        raise HTTPException(status_code=400, detail="notify_on must be 'all', 'failed', or 'critical_only'")

    db: AsyncSession = current["db"]
    tenant_id = current["tenant_id"]

    # Upsert by tenant + type
    result = await db.execute(
        select(NotificationConfig).where(
            NotificationConfig.tenant_id == tenant_id,
            NotificationConfig.type == req.type,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.webhook_url = req.webhook_url
        existing.enabled = req.enabled
        existing.notify_on = req.notify_on
    else:
        config = NotificationConfig(
            tenant_id=tenant_id,
            type=req.type,
            webhook_url=req.webhook_url,
            enabled=req.enabled,
            notify_on=req.notify_on,
        )
        db.add(config)

    await db.commit()
    return {"message": f"{req.type.title()} notification configured"}


@router.get("/config")
async def list_notification_configs(current: dict = Depends(get_current_tenant)):
    db: AsyncSession = current["db"]
    tenant_id = current["tenant_id"]

    result = await db.execute(
        select(NotificationConfig).where(NotificationConfig.tenant_id == tenant_id)
    )
    configs = result.scalars().all()

    return {
        "configs": [
            {
                "id": c.id,
                "type": c.type,
                "webhook_url": c.webhook_url,
                "enabled": c.enabled,
                "notify_on": c.notify_on,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in configs
        ]
    }


@router.post("/test")
async def test_notification(req: NotificationConfigRequest, current: dict = Depends(get_current_tenant)):
    """Send a test notification."""
    test_result = {
        "summary": {
            "repo_url": "https://github.com/example/test-repo",
            "status": "completed",
            "total_issues": 5,
            "tests_passed": 10,
            "tests_failed": 2,
            "by_severity": {"critical": 1, "high": 2, "medium": 1, "low": 1},
        }
    }
    try:
        await send_notification(req.type, req.webhook_url, test_result)
        return {"message": "Test notification sent successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to send test notification: {e}")


@router.delete("/config/{config_id}")
async def delete_notification_config(config_id: str, current: dict = Depends(get_current_tenant)):
    db: AsyncSession = current["db"]
    tenant_id = current["tenant_id"]

    result = await db.execute(
        select(NotificationConfig).where(
            NotificationConfig.id == config_id,
            NotificationConfig.tenant_id == tenant_id,
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Notification config not found")

    await db.delete(config)
    await db.commit()
    return {"message": "Notification config deleted"}
