import secrets
import uuid
import logging
from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db, async_session
from app.core.db_models import Tenant, WebhookConfig, ScanRecord
from app.core.models import ScanRequest, RepoSource
from app.core.pipeline import run_scan

logger = logging.getLogger("reporat.webhooks")

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


async def _validate_webhook(tenant_slug: str, secret: str, db: AsyncSession, source: str) -> Tenant:
    """Validate tenant slug + secret. Returns tenant or raises 401/404."""
    result = await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    wh_result = await db.execute(
        select(WebhookConfig).where(
            WebhookConfig.tenant_id == tenant.id,
            WebhookConfig.source == source,
            WebhookConfig.secret == secret,
            WebhookConfig.auto_scan == True,
        )
    )
    config = wh_result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    return tenant


async def _trigger_webhook_scan(
    tenant_id: str,
    owner_id: str,
    repo_url: str,
    branch: str,
    repo_source: RepoSource,
):
    """Create scan record and run scan in background."""
    async with async_session() as db:
        scan_id = str(uuid.uuid4())
        record = ScanRecord(
            id=scan_id,
            tenant_id=tenant_id,
            triggered_by=owner_id,
            repo_url=repo_url,
            branch=branch,
            repo_source=repo_source.value,
            status="pending",
        )
        db.add(record)
        await db.commit()

        request = ScanRequest(
            repo_url=repo_url,
            branch=branch,
            repo_source=repo_source,
            file_bugs=False,
        )
        await run_scan(request, scan_id=scan_id, db=db, scan_record_id=scan_id)


@router.post("/github")
async def github_webhook(
    request: Request,
    bg: BackgroundTasks,
    tenant: str = "",
    secret: str = "",
    db: AsyncSession = Depends(get_db),
):
    """Receive GitHub push webhook."""
    if not tenant or not secret:
        raise HTTPException(status_code=400, detail="Missing tenant or secret query params")

    tenant_obj = await _validate_webhook(tenant, secret, db, "github")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    try:
        repository = payload.get("repository") or {}
        repo_url = repository.get("clone_url") or repository.get("html_url", "")
        ref = payload.get("ref", "")
        branch = ref.replace("refs/heads/", "") if ref.startswith("refs/heads/") else ref or "main"
    except Exception:
        raise HTTPException(status_code=400, detail="Malformed payload: could not extract repo/branch")

    if not repo_url:
        raise HTTPException(status_code=400, detail="Could not extract repo URL from payload")

    scan_id = str(uuid.uuid4())
    bg.add_task(_trigger_webhook_scan, tenant_obj.id, tenant_obj.owner_id, repo_url, branch, RepoSource.GITHUB)
    return {"message": "Scan triggered", "scan_id": scan_id, "repo": repo_url, "branch": branch}


@router.post("/gitlab")
async def gitlab_webhook(
    request: Request,
    bg: BackgroundTasks,
    tenant: str = "",
    secret: str = "",
    db: AsyncSession = Depends(get_db),
):
    """Receive GitLab push webhook."""
    if not tenant or not secret:
        raise HTTPException(status_code=400, detail="Missing tenant or secret query params")

    tenant_obj = await _validate_webhook(tenant, secret, db, "gitlab")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    try:
        project = payload.get("project") or {}
        repo_url = project.get("git_http_url", "")
        ref = payload.get("ref", "")
        branch = ref.replace("refs/heads/", "") if ref.startswith("refs/heads/") else ref or "main"
    except Exception:
        raise HTTPException(status_code=400, detail="Malformed payload: could not extract repo/branch")

    if not repo_url:
        raise HTTPException(status_code=400, detail="Could not extract repo URL from payload")

    scan_id = str(uuid.uuid4())
    bg.add_task(_trigger_webhook_scan, tenant_obj.id, tenant_obj.owner_id, repo_url, branch, RepoSource.GITLAB)
    return {"message": "Scan triggered", "scan_id": scan_id, "repo": repo_url, "branch": branch}


@router.post("/azure")
async def azure_webhook(
    request: Request,
    bg: BackgroundTasks,
    tenant: str = "",
    secret: str = "",
    db: AsyncSession = Depends(get_db),
):
    """Receive Azure DevOps push webhook."""
    if not tenant or not secret:
        raise HTTPException(status_code=400, detail="Missing tenant or secret query params")

    tenant_obj = await _validate_webhook(tenant, secret, db, "azure_devops")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    try:
        resource = payload.get("resource") or {}
        repository = resource.get("repository") or {}
        repo_url = repository.get("remoteUrl", "")

        ref_updates = resource.get("refUpdates") or []
        if ref_updates:
            ref = ref_updates[0].get("name", "")
        else:
            ref = ""
        branch = ref.replace("refs/heads/", "") if ref.startswith("refs/heads/") else ref or "main"
    except Exception:
        raise HTTPException(status_code=400, detail="Malformed payload: could not extract repo/branch")

    if not repo_url:
        raise HTTPException(status_code=400, detail="Could not extract repo URL from payload")

    scan_id = str(uuid.uuid4())
    bg.add_task(_trigger_webhook_scan, tenant_obj.id, tenant_obj.owner_id, repo_url, branch, RepoSource.AZURE_DEVOPS)
    return {"message": "Scan triggered", "scan_id": scan_id, "repo": repo_url, "branch": branch}
