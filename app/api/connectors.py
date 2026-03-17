from fastapi import APIRouter, HTTPException
from app.core.models import BugTrackerType
from app.services.bug_reporter import get_tracker

router = APIRouter(prefix="/api/connectors", tags=["connectors"])


@router.get("")
async def list_connectors():
    results = []
    for tracker_type in BugTrackerType:
        try:
            tracker = get_tracker(tracker_type)
            connected = await tracker.test_connection()
        except Exception:
            connected = False
        results.append({"type": tracker_type.value, "connected": connected})
    return {"connectors": results}


@router.post("/{tracker_type}/test")
async def test_connector(tracker_type: BugTrackerType):
    try:
        tracker = get_tracker(tracker_type)
        connected = await tracker.test_connection()
        return {
            "type": tracker_type.value,
            "connected": connected,
            "message": "Connection successful" if connected else "Connection failed",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
