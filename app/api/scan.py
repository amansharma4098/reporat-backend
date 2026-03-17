import uuid
import json
from fastapi import APIRouter, BackgroundTasks, HTTPException, WebSocket, WebSocketDisconnect
from app.core.models import ScanRequest
from app.core.pipeline import run_scan, get_scan, get_all_scans, scan_store, register_callback

router = APIRouter(prefix="/api/scan", tags=["scan"])


@router.post("")
async def trigger_scan(request: ScanRequest, bg: BackgroundTasks):
    scan_id = str(uuid.uuid4())
    bg.add_task(run_scan, request, scan_id)
    return {
        "scan_id": scan_id,
        "status": "pending",
        "message": f"Scan queued for {request.repo_url}",
    }


@router.get("")
async def list_scans():
    return {"scans": get_all_scans()}


@router.get("/{scan_id}")
async def get_scan_status(scan_id: str):
    scan = get_scan(scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
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


@router.get("/{scan_id}/summary")
async def get_scan_summary(scan_id: str):
    scan = get_scan(scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    return scan.summary


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
