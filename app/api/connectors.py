import json
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.models import BugTrackerType
from app.core.database import get_db
from app.core.db_models import ConnectorConfig as ConnectorConfigDB
from app.api.deps import get_current_tenant
from app.services.bug_reporter import get_tracker

router = APIRouter(prefix="/api/connectors", tags=["connectors"])

# Credential schema per tracker type
CONNECTOR_SCHEMAS = {
    "jira": {
        "url": {"type": "string", "label": "Jira URL", "placeholder": "https://your-domain.atlassian.net"},
        "email": {"type": "string", "label": "Email"},
        "api_token": {"type": "string", "label": "API Token", "secret": True},
        "project_key": {"type": "string", "label": "Project Key", "placeholder": "PROJ"},
    },
    "azure_boards": {
        "org": {"type": "string", "label": "Organization"},
        "project": {"type": "string", "label": "Project"},
        "pat": {"type": "string", "label": "Personal Access Token", "secret": True},
    },
    "github_issues": {
        "pat": {"type": "string", "label": "Personal Access Token", "secret": True},
        "repo": {"type": "string", "label": "Repository", "placeholder": "owner/repo"},
    },
    "linear": {
        "api_key": {"type": "string", "label": "API Key", "secret": True},
        "team_id": {"type": "string", "label": "Team ID"},
    },
}


REQUIRED_FIELDS = {
    "jira": ["url", "email", "api_token", "project_key"],
    "azure_boards": ["org", "project", "pat"],
    "github_issues": ["pat", "repo"],
    "linear": ["api_key", "team_id"],
}


def _validate_credentials(tracker_type: str, credentials: dict):
    required = REQUIRED_FIELDS.get(tracker_type, [])
    missing = [f for f in required if not credentials.get(f)]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Missing required fields: {', '.join(missing)}",
        )


class TestCredentials(BaseModel):
    credentials: dict


class SaveCredentials(BaseModel):
    credentials: dict


@router.get("/schema")
async def get_connector_schema():
    """Returns the required credential fields per tracker type."""
    return {"schemas": CONNECTOR_SCHEMAS}


@router.get("")
async def list_connectors(current: dict = Depends(get_current_tenant)):
    db: AsyncSession = current["db"]
    tenant_id = current["tenant_id"]

    result = await db.execute(
        select(ConnectorConfigDB).where(ConnectorConfigDB.tenant_id == tenant_id)
    )
    configs = result.scalars().all()

    saved_types = {c.tracker_type for c in configs}
    connectors = []
    for tracker_type in BugTrackerType:
        connectors.append({
            "type": tracker_type.value,
            "configured": tracker_type.value in saved_types,
        })
    return {"connectors": connectors}


@router.post("/{tracker_type}/test")
async def test_connector(tracker_type: BugTrackerType, req: TestCredentials):
    """Test connection with inline credentials."""
    _validate_credentials(tracker_type.value, req.credentials)
    try:
        tracker = get_tracker(tracker_type, req.credentials)
        connected = await tracker.test_connection()
        return {
            "type": tracker_type.value,
            "connected": connected,
            "message": "Connection successful" if connected else "Connection failed — check token permissions and repo name",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{tracker_type}/config")
async def save_connector_config(
    tracker_type: BugTrackerType,
    req: SaveCredentials,
    current: dict = Depends(get_current_tenant),
):
    """Save connector credentials for the tenant."""
    _validate_credentials(tracker_type.value, req.credentials)
    db: AsyncSession = current["db"]
    tenant_id = current["tenant_id"]
    user_id = current["user"].id

    # Upsert: check if config already exists
    result = await db.execute(
        select(ConnectorConfigDB).where(
            ConnectorConfigDB.tenant_id == tenant_id,
            ConnectorConfigDB.tracker_type == tracker_type.value,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.credentials_json = json.dumps(req.credentials)
        existing.updated_by = user_id
    else:
        config = ConnectorConfigDB(
            tenant_id=tenant_id,
            tracker_type=tracker_type.value,
            credentials_json=json.dumps(req.credentials),
            updated_by=user_id,
        )
        db.add(config)

    await db.commit()
    return {"message": f"Saved {tracker_type.value} config", "type": tracker_type.value}
