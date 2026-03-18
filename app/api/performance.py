import asyncio
import json
import uuid
from datetime import datetime, timezone
from dataclasses import asdict
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant
from app.core.db_models import PerformanceTestResult
from app.analyzers.api_loadtest import run_api_loadtest
from app.analyzers.frontend_perf import analyze_frontend_performance

router = APIRouter(prefix="/api/performance", tags=["performance"])


# --- Request models ---

class EndpointSpec(BaseModel):
    method: str = "GET"
    path: str
    headers: dict = {}
    body: dict | None = None


class LoadTestRequest(BaseModel):
    target_url: str
    endpoints: list[EndpointSpec] | None = None
    concurrent_users: int = 10
    duration_seconds: int = 30


class FrontendPerfRequest(BaseModel):
    url: str


# --- Background runner ---

async def _run_loadtest_background(test_id: str, tenant_id: str, req: LoadTestRequest):
    """Run load test and persist results."""
    from app.core.database import async_session
    try:
        endpoints = [ep.model_dump() for ep in req.endpoints] if req.endpoints else None
        result = await run_api_loadtest(
            base_url=req.target_url,
            endpoints=endpoints,
            concurrent_users=req.concurrent_users,
            duration_seconds=req.duration_seconds,
        )
        results_json = json.dumps(asdict(result))
        status = "completed"
    except Exception as e:
        results_json = json.dumps({"error": str(e)})
        status = "failed"

    async with async_session() as session:
        from sqlalchemy import update
        await session.execute(
            update(PerformanceTestResult)
            .where(PerformanceTestResult.id == test_id)
            .values(
                results_json=results_json,
                status=status,
                completed_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()


# --- Endpoints ---

@router.post("/loadtest")
async def start_load_test(req: LoadTestRequest, current: dict = Depends(get_current_tenant)):
    db: AsyncSession = current["db"]
    tenant_id = current["tenant_id"]

    # Validate URL
    if not req.target_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="target_url must be a valid HTTP(S) URL")

    test_id = str(uuid.uuid4())

    # Create record
    record = PerformanceTestResult(
        id=test_id,
        tenant_id=tenant_id,
        type="loadtest",
        target_url=req.target_url,
        status="running",
    )
    db.add(record)
    await db.commit()

    # Run in background
    asyncio.create_task(_run_loadtest_background(test_id, tenant_id, req))

    return {"test_id": test_id, "status": "running"}


@router.get("/loadtest/{test_id}")
async def get_load_test_result(test_id: str, current: dict = Depends(get_current_tenant)):
    db: AsyncSession = current["db"]
    tenant_id = current["tenant_id"]

    result = await db.execute(
        select(PerformanceTestResult).where(
            PerformanceTestResult.id == test_id,
            PerformanceTestResult.tenant_id == tenant_id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Test not found")

    return {
        "test_id": record.id,
        "type": record.type,
        "target_url": record.target_url,
        "status": record.status,
        "results": json.loads(record.results_json) if record.results_json else None,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "completed_at": record.completed_at.isoformat() if record.completed_at else None,
    }


@router.post("/frontend")
async def analyze_frontend(req: FrontendPerfRequest, current: dict = Depends(get_current_tenant)):
    db: AsyncSession = current["db"]
    tenant_id = current["tenant_id"]

    if not req.url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="url must be a valid HTTP(S) URL")

    results = await analyze_frontend_performance(req.url)

    # Save to DB
    test_id = str(uuid.uuid4())
    record = PerformanceTestResult(
        id=test_id,
        tenant_id=tenant_id,
        type="frontend",
        target_url=req.url,
        results_json=json.dumps(results),
        status="completed",
        completed_at=datetime.now(timezone.utc),
    )
    db.add(record)
    await db.commit()

    return {"test_id": test_id, **results}


@router.get("/tests")
async def list_performance_tests(current: dict = Depends(get_current_tenant)):
    db: AsyncSession = current["db"]
    tenant_id = current["tenant_id"]

    result = await db.execute(
        select(PerformanceTestResult)
        .where(PerformanceTestResult.tenant_id == tenant_id)
        .order_by(PerformanceTestResult.created_at.desc())
    )
    records = result.scalars().all()

    return [
        {
            "test_id": r.id,
            "type": r.type,
            "target_url": r.target_url,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in records
    ]
