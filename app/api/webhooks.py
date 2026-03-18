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
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    return tenant


async def _trigger_webhook_scan(tenant_id: str, owner_id: str, repo_url: str, branch: str, repo_source: RepoSource):
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

        request = ScanRequest(repo_url=repo_url, branch=branch, repo_source=repo_source)
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
    payload = await request.json()

    repo_url = payload.get("repository", {}).get("clone_url") or payload.get("repository", {}).get("html_url", "")
    ref = payload.get("ref", "refs/heads/main")
    branch = ref.split("/")[-1] if "/" in ref else ref

    if not repo_url:
        raise HTTPException(status_code=400, detail="Could not extract repo URL from payload")

    bg.add_task(_trigger_webhook_scan, tenant_obj.id, tenant_obj.owner_id, repo_url, branch, RepoSource.GITHUB)
    return {"message": "Scan triggered", "repo": repo_url, "branch": branch}


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
    payload = await request.json()

    repo_url = payload.get("repository", {}).get("git_http_url") or payload.get("project", {}).get("http_url", "")
    ref = payload.get("ref", "refs/heads/main")
    branch = ref.split("/")[-1] if "/" in ref else ref

    if not repo_url:
        raise HTTPException(status_code=400, detail="Could not extract repo URL from payload")

    bg.add_task(_trigger_webhook_scan, tenant_obj.id, tenant_obj.owner_id, repo_url, branch, RepoSource.GITLAB)
    return {"message": "Scan triggered", "repo": repo_url, "branch": branch}


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
    payload = await request.json()

    resource = payload.get("resource", {})
    repo_url = resource.get("repository", {}).get("remoteUrl", "")
    ref = resource.get("refUpdates", [{}])[0].get("name", "refs/heads/main") if resource.get("refUpdates") else "refs/heads/main"
    branch = ref.split("/")[-1] if "/" in ref else ref

    if not repo_url:
        raise HTTPException(status_code=400, detail="Could not extract repo URL from payload")

    bg.add_task(_trigger_webhook_scan, tenant_obj.id, tenant_obj.owner_id, repo_url, branch, RepoSource.AZURE_DEVOPS)
    return {"message": "Scan triggered", "repo": repo_url, "branch": branch}
