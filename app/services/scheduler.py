import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import select

from app.core.database import async_session
from app.core.db_models import ScanSchedule, ScanRecord, Tenant
from app.core.models import ScanRequest, RepoSource
from app.core.pipeline import run_scan

logger = logging.getLogger("reporat.scheduler")


async def _run_scheduled_scan(schedule: ScanSchedule, tenant_owner_id: str):
    """Run a single scheduled scan."""
    async with async_session() as db:
        scan_id = str(uuid.uuid4())
        repo_source = RepoSource(schedule.repo_source) if schedule.repo_source else RepoSource.GITHUB

        record = ScanRecord(
            id=scan_id,
            tenant_id=schedule.tenant_id,
            triggered_by=tenant_owner_id,
            repo_url=schedule.repo_url,
            branch=schedule.branch or "main",
            repo_source=repo_source.value,
            status="pending",
        )
        db.add(record)
        await db.commit()

        request = ScanRequest(
            repo_url=schedule.repo_url,
            branch=schedule.branch or "main",
            repo_source=repo_source,
        )
        await run_scan(request, scan_id=scan_id, db=db, scan_record_id=scan_id)


async def _check_schedules():
    """Check for due schedules and trigger scans."""
    async with async_session() as db:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(ScanSchedule).where(
                ScanSchedule.enabled == True,
                ScanSchedule.next_run <= now,
            )
        )
        due_schedules = result.scalars().all()

        for schedule in due_schedules:
            try:
                # Get tenant owner for triggered_by
                tenant_result = await db.execute(
                    select(Tenant).where(Tenant.id == schedule.tenant_id)
                )
                tenant = tenant_result.scalar_one_or_none()
                if not tenant:
                    continue

                # Update schedule timing
                schedule.last_run = now
                interval = schedule.interval_hours or 24
                schedule.next_run = now + timedelta(hours=interval)
                await db.commit()

                # Run scan in background task
                asyncio.create_task(_run_scheduled_scan(schedule, tenant.owner_id))
                logger.info(f"Triggered scheduled scan for {schedule.repo_url}")

            except Exception as e:
                logger.error(f"Failed to trigger scheduled scan {schedule.id}: {e}")


async def start_scheduler():
    """Background loop that checks for due schedules every 60 seconds."""
    logger.info("Scan scheduler started")
    while True:
        try:
            await _check_schedules()
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
        await asyncio.sleep(60)
