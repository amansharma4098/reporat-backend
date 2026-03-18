from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone, timedelta

from app.core.db_models import ScanSchedule
from app.core.models import RepoSource
from app.api.deps import get_current_tenant

router = APIRouter(prefix="/api/schedules", tags=["schedules"])


class CreateScheduleRequest(BaseModel):
    repo_url: str
    branch: str = "main"
    repo_source: str = "github"
    interval_hours: int = 24
    cron_expression: str | None = None


class ToggleScheduleRequest(BaseModel):
    enabled: bool


@router.post("")
async def create_schedule(req: CreateScheduleRequest, current: dict = Depends(get_current_tenant)):
    if req.interval_hours < 1:
        raise HTTPException(status_code=400, detail="interval_hours must be at least 1")

    db: AsyncSession = current["db"]
    tenant_id = current["tenant_id"]

    now = datetime.now(timezone.utc)
    schedule = ScanSchedule(
        tenant_id=tenant_id,
        repo_url=req.repo_url,
        branch=req.branch,
        repo_source=req.repo_source,
        cron_expression=req.cron_expression,
        interval_hours=req.interval_hours,
        enabled=True,
        next_run=now + timedelta(hours=req.interval_hours),
    )
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)

    return {
        "id": schedule.id,
        "repo_url": schedule.repo_url,
        "branch": schedule.branch,
        "interval_hours": schedule.interval_hours,
        "enabled": schedule.enabled,
        "next_run": schedule.next_run.isoformat() if schedule.next_run else None,
        "message": "Schedule created",
    }


@router.get("")
async def list_schedules(current: dict = Depends(get_current_tenant)):
    db: AsyncSession = current["db"]
    tenant_id = current["tenant_id"]

    result = await db.execute(
        select(ScanSchedule).where(ScanSchedule.tenant_id == tenant_id)
    )
    schedules = result.scalars().all()

    return {
        "schedules": [
            {
                "id": s.id,
                "repo_url": s.repo_url,
                "branch": s.branch,
                "repo_source": s.repo_source,
                "interval_hours": s.interval_hours,
                "cron_expression": s.cron_expression,
                "enabled": s.enabled,
                "last_run": s.last_run.isoformat() if s.last_run else None,
                "next_run": s.next_run.isoformat() if s.next_run else None,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in schedules
        ]
    }


@router.delete("/{schedule_id}")
async def delete_schedule(schedule_id: str, current: dict = Depends(get_current_tenant)):
    db: AsyncSession = current["db"]
    tenant_id = current["tenant_id"]

    result = await db.execute(
        select(ScanSchedule).where(
            ScanSchedule.id == schedule_id,
            ScanSchedule.tenant_id == tenant_id,
        )
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    await db.delete(schedule)
    await db.commit()
    return {"message": "Schedule deleted"}


@router.patch("/{schedule_id}")
async def toggle_schedule(schedule_id: str, req: ToggleScheduleRequest, current: dict = Depends(get_current_tenant)):
    db: AsyncSession = current["db"]
    tenant_id = current["tenant_id"]

    result = await db.execute(
        select(ScanSchedule).where(
            ScanSchedule.id == schedule_id,
            ScanSchedule.tenant_id == tenant_id,
        )
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    schedule.enabled = req.enabled
    if req.enabled and not schedule.next_run:
        schedule.next_run = datetime.now(timezone.utc) + timedelta(hours=schedule.interval_hours or 24)
    await db.commit()

    return {
        "id": schedule.id,
        "enabled": schedule.enabled,
        "next_run": schedule.next_run.isoformat() if schedule.next_run else None,
        "message": f"Schedule {'enabled' if req.enabled else 'disabled'}",
    }
