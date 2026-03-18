import json
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks, HTTPException, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from fastapi.responses import Response
from app.core.models import ScanRequest, FileBugsRequest, FileBugsSavedRequest, Issue, BugTrackerType
from app.services.scan_diff import compute_diff
from app.services.report_generator import generate_pdf
from app.core.pipeline import run_scan, get_scan, get_all_scans, scan_store, register_callback
from app.core.database import get_db, async_session
from app.core.db_models import ScanRecord, ConnectorConfig as ConnectorConfigDB
from app.api.deps import get_current_tenant
from app.services.bug_reporter import file_bugs, get_tracker

router = APIRouter(prefix="/api/scan", tags=["scan"])


async def _run_scan_with_db(request: ScanRequest, scan_id: str, scan_record_id: str):
    """Wrapper to run scan with its own DB session for background tasks."""
    async with async_session() as db:
        await run_scan(request, scan_id=scan_id, db=db, scan_record_id=scan_record_id)


@router.post("")
async def trigger_scan(
    request: ScanRequest,
    bg: BackgroundTasks,
    current: dict = Depends(get_current_tenant),
):
    scan_id = str(uuid.uuid4())
    db: AsyncSession = current["db"]

    # Create scan record in DB
    record = ScanRecord(
        id=scan_id,
        tenant_id=current["tenant_id"],
        triggered_by=current["user"].id,
        repo_url=request.repo_url,
        branch=request.branch,
        repo_source=request.repo_source.value,
        status="pending",
    )
    db.add(record)
    await db.commit()

    bg.add_task(_run_scan_with_db, request, scan_id, scan_id)
    return {
        "scan_id": scan_id,
        "status": "pending",
        "message": f"Scan queued for {request.repo_url}",
    }


@router.get("")
async def list_scans(current: dict = Depends(get_current_tenant)):
    db: AsyncSession = current["db"]
    tenant_id = current["tenant_id"]

    result = await db.execute(
        select(ScanRecord)
        .where(ScanRecord.tenant_id == tenant_id)
        .order_by(ScanRecord.created_at.desc())
    )
    records = result.scalars().all()

    scans = []
    for r in records:
        # Try in-memory store first for active scans
        in_mem = scan_store.get(r.id)
        if in_mem:
            scans.append(in_mem.summary)
        else:
            try:
                summary = json.loads(r.summary_json) if r.summary_json else None
            except (json.JSONDecodeError, TypeError):
                summary = None
            scans.append({
                "scan_id": r.id,
                "repo_url": r.repo_url,
                "status": r.status,
                "started_at": r.created_at.isoformat() if r.created_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "summary": summary,
            })
    return {"scans": scans}


@router.get("/{scan_id}")
async def get_scan_status(scan_id: str, current: dict = Depends(get_current_tenant)):
    db: AsyncSession = current["db"]
    tenant_id = current["tenant_id"]

    # Verify ownership
    result = await db.execute(
        select(ScanRecord).where(ScanRecord.id == scan_id, ScanRecord.tenant_id == tenant_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Scan not found")

    # Try in-memory store first
    scan = scan_store.get(scan_id)
    if scan:
        return {
            "scan_id": scan_id,
            "status": scan.status.value,
            "summary": scan.summary,
            "issues": [i.model_dump() for i in scan.issues],
            "generated_tests": [t.model_dump() for t in scan.generated_tests],
            "test_results": [t.model_dump() for t in scan.test_results],
            "bugs_filed": scan.bugs_filed,
            "error": scan.error,
        }

    # Fall back to DB — parse JSON safely
    def _safe_json(val, default):
        if not val:
            return default
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return default

    return {
        "scan_id": scan_id,
        "status": record.status,
        "summary": _safe_json(record.summary_json, None),
        "issues": _safe_json(record.issues_json, []),
        "generated_tests": [],
        "test_results": _safe_json(record.test_results_json, []),
        "bugs_filed": _safe_json(record.bugs_filed_json, []),
        "error": record.error,
    }


@router.get("/{scan_id}/summary")
async def get_scan_summary(scan_id: str, current: dict = Depends(get_current_tenant)):
    db: AsyncSession = current["db"]
    result = await db.execute(
        select(ScanRecord).where(
            ScanRecord.id == scan_id, ScanRecord.tenant_id == current["tenant_id"]
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Scan not found")

    scan = scan_store.get(scan_id)
    if scan:
        return scan.summary

    if record.summary_json:
        try:
            return json.loads(record.summary_json)
        except (json.JSONDecodeError, TypeError):
            pass
    return {"scan_id": scan_id, "status": record.status}


@router.post("/{scan_id}/file-bugs")
async def file_bugs_inline(
    scan_id: str,
    req: FileBugsRequest,
    current: dict = Depends(get_current_tenant),
):
    """File bugs using inline credentials provided in the request."""
    db: AsyncSession = current["db"]
    tenant_id = current["tenant_id"]

    # Verify scan ownership and completion
    result = await db.execute(
        select(ScanRecord).where(ScanRecord.id == scan_id, ScanRecord.tenant_id == tenant_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Scan not found")
    if record.status != "completed":
        raise HTTPException(status_code=400, detail=f"Scan is not completed (status: {record.status})")

    # Get issues from in-memory or DB
    issues = _get_issues(scan_id, record)
    if not issues:
        raise HTTPException(status_code=400, detail="No issues found in scan results")

    # Filter by issue_ids if provided
    if req.issue_ids:
        issues = [i for i in issues if i.id in req.issue_ids]
        if not issues:
            raise HTTPException(status_code=400, detail="None of the specified issue IDs found")

    # Validate credentials by testing connection
    tracker = get_tracker(req.tracker_type, req.credentials)
    connected = await tracker.test_connection()
    if not connected:
        raise HTTPException(status_code=400, detail=f"Failed to connect to {req.tracker_type.value}. Check credentials.")

    # File bugs
    filed = await tracker.file_bugs(issues)

    # Update scan record
    try:
        existing_filed = json.loads(record.bugs_filed_json) if record.bugs_filed_json else []
    except (json.JSONDecodeError, TypeError):
        existing_filed = []
    existing_filed.extend(filed)
    record.bugs_filed_json = json.dumps(existing_filed)
    await db.commit()

    # Update in-memory store too
    scan = scan_store.get(scan_id)
    if scan:
        scan.bugs_filed.extend(filed)

    return {"filed": len(filed), "bugs": filed}


@router.post("/{scan_id}/file-bugs/saved")
async def file_bugs_saved(
    scan_id: str,
    req: FileBugsSavedRequest,
    current: dict = Depends(get_current_tenant),
):
    """File bugs using tenant's saved connector config."""
    db: AsyncSession = current["db"]
    tenant_id = current["tenant_id"]

    # Verify scan ownership and completion
    result = await db.execute(
        select(ScanRecord).where(ScanRecord.id == scan_id, ScanRecord.tenant_id == tenant_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Scan not found")
    if record.status != "completed":
        raise HTTPException(status_code=400, detail=f"Scan is not completed (status: {record.status})")

    # Get saved connector config
    config_result = await db.execute(
        select(ConnectorConfigDB).where(
            ConnectorConfigDB.tenant_id == tenant_id,
            ConnectorConfigDB.tracker_type == req.tracker_type.value,
        )
    )
    config = config_result.scalar_one_or_none()
    if not config:
        raise HTTPException(
            status_code=404,
            detail=f"No saved config for {req.tracker_type.value}. Save credentials first.",
        )

    credentials = json.loads(config.credentials_json)

    # Get issues
    issues = _get_issues(scan_id, record)
    if not issues:
        raise HTTPException(status_code=400, detail="No issues found in scan results")

    if req.issue_ids:
        issues = [i for i in issues if i.id in req.issue_ids]
        if not issues:
            raise HTTPException(status_code=400, detail="None of the specified issue IDs found")

    # Test connection and file
    tracker = get_tracker(req.tracker_type, credentials)
    connected = await tracker.test_connection()
    if not connected:
        raise HTTPException(status_code=400, detail=f"Failed to connect to {req.tracker_type.value}. Check saved credentials.")

    filed = await tracker.file_bugs(issues)

    # Update scan record
    try:
        existing_filed = json.loads(record.bugs_filed_json) if record.bugs_filed_json else []
    except (json.JSONDecodeError, TypeError):
        existing_filed = []
    existing_filed.extend(filed)
    record.bugs_filed_json = json.dumps(existing_filed)
    await db.commit()

    scan = scan_store.get(scan_id)
    if scan:
        scan.bugs_filed.extend(filed)

    return {"filed": len(filed), "bugs": filed}


@router.delete("/{scan_id}")
async def delete_scan(scan_id: str, current: dict = Depends(get_current_tenant)):
    """Delete a single scan by ID."""
    db: AsyncSession = current["db"]
    tenant_id = current["tenant_id"]

    result = await db.execute(
        select(ScanRecord).where(ScanRecord.id == scan_id, ScanRecord.tenant_id == tenant_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Scan not found")

    await db.delete(record)
    await db.commit()
    scan_store.pop(scan_id, None)
    return {"message": "Scan deleted"}


@router.delete("")
async def delete_all_scans(all: bool = False, current: dict = Depends(get_current_tenant)):
    """Delete all scans for the current tenant when all=true."""
    if not all:
        raise HTTPException(status_code=400, detail="Pass ?all=true to delete all scans")

    db: AsyncSession = current["db"]
    tenant_id = current["tenant_id"]

    # Get IDs first to clean up in-memory store
    result = await db.execute(
        select(ScanRecord.id).where(ScanRecord.tenant_id == tenant_id)
    )
    scan_ids = [row[0] for row in result.all()]

    await db.execute(
        delete(ScanRecord).where(ScanRecord.tenant_id == tenant_id)
    )
    await db.commit()

    for sid in scan_ids:
        scan_store.pop(sid, None)

    return {"message": f"{len(scan_ids)} scans deleted"}


@router.get("/{scan_id}/diff")
async def get_scan_diff(scan_id: str, current: dict = Depends(get_current_tenant)):
    """Compare current scan with previous scan for the same repo."""
    db: AsyncSession = current["db"]
    tenant_id = current["tenant_id"]

    result = await db.execute(
        select(ScanRecord).where(ScanRecord.id == scan_id, ScanRecord.tenant_id == tenant_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Scan not found")

    current_issues = _get_issues(scan_id, record)

    # Find previous completed scan for same repo
    prev_result = await db.execute(
        select(ScanRecord)
        .where(
            ScanRecord.tenant_id == tenant_id,
            ScanRecord.repo_url == record.repo_url,
            ScanRecord.status == "completed",
            ScanRecord.id != scan_id,
            ScanRecord.created_at < record.created_at,
        )
        .order_by(ScanRecord.created_at.desc())
        .limit(1)
    )
    prev_record = prev_result.scalar_one_or_none()

    if prev_record:
        previous_issues = _get_issues(prev_record.id, prev_record)
    else:
        previous_issues = []

    return compute_diff(current_issues, previous_issues)


@router.get("/{scan_id}/report")
async def get_scan_report(scan_id: str, current: dict = Depends(get_current_tenant)):
    """Generate and return a PDF report for the scan."""
    db: AsyncSession = current["db"]
    tenant_id = current["tenant_id"]

    result = await db.execute(
        select(ScanRecord).where(ScanRecord.id == scan_id, ScanRecord.tenant_id == tenant_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Scan not found")

    # Build scan data dict
    def _safe_json(val, default):
        if not val:
            return default
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return default

    scan = scan_store.get(scan_id)
    if scan:
        scan_data = {
            "summary": scan.summary,
            "issues": [i.model_dump() for i in scan.issues],
        }
    else:
        scan_data = {
            "summary": _safe_json(record.summary_json, {
                "repo_url": record.repo_url,
                "status": record.status,
                "started_at": record.created_at.isoformat() if record.created_at else "N/A",
                "completed_at": record.completed_at.isoformat() if record.completed_at else "N/A",
                "total_issues": 0,
                "by_severity": {},
                "tests_passed": 0,
                "tests_failed": 0,
            }),
            "issues": _safe_json(record.issues_json, []),
        }

    pdf_bytes = generate_pdf(scan_data)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=reporat-scan-{scan_id[:8]}.pdf"},
    )


def _get_issues(scan_id: str, record: ScanRecord) -> list[Issue]:
    """Retrieve issues from in-memory store or DB record."""
    scan = scan_store.get(scan_id)
    if scan:
        return list(scan.issues)

    if record.issues_json:
        try:
            raw = json.loads(record.issues_json)
            return [Issue(**i) for i in raw] if raw else []
        except (json.JSONDecodeError, TypeError):
            return []
    return []


@router.websocket("/ws/{scan_id}")
async def scan_websocket(websocket: WebSocket, scan_id: str):
    await websocket.accept()

    async def send_update(data: dict):
        try:
            await websocket.send_json(data)
        except Exception:
            pass

    register_callback(scan_id, send_update)

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
