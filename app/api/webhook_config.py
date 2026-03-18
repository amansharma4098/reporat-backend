import secrets
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.db_models import WebhookConfig
from app.api.deps import get_current_tenant

router = APIRouter(prefix="/api/webhooks/config", tags=["webhooks"])


class WebhookConfigRequest(BaseModel):
    source: str  # github, gitlab, azure_devops
    auto_scan: bool = True


def _build_webhook_url(source: str, tenant_slug: str, secret: str) -> str:
    source_path = {"github": "github", "gitlab": "gitlab", "azure_devops": "azure"}.get(source, source)
    return f"https://api.reporat.com/api/webhooks/{source_path}?tenant={tenant_slug}&secret={secret}"


@router.post("")
async def save_webhook_config(req: WebhookConfigRequest, current: dict = Depends(get_current_tenant)):
    if current["role"] not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can configure webhooks")

    valid_sources = ("github", "gitlab", "azure_devops")
    if req.source not in valid_sources:
        raise HTTPException(status_code=400, detail=f"Source must be one of: {', '.join(valid_sources)}")

    db: AsyncSession = current["db"]
    tenant_id = current["tenant_id"]
    tenant_slug = current["tenant"].slug

    # Check for existing config for this source
    result = await db.execute(
        select(WebhookConfig).where(
            WebhookConfig.tenant_id == tenant_id,
            WebhookConfig.source == req.source,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.auto_scan = req.auto_scan
        await db.commit()
        await db.refresh(existing)
        return {
            "id": existing.id,
            "message": f"Webhook configured for {req.source}",
            "source": req.source,
            "secret": existing.secret,
            "webhook_url": _build_webhook_url(req.source, tenant_slug, existing.secret),
            "auto_scan": req.auto_scan,
            "created_at": existing.created_at.isoformat() if existing.created_at else None,
        }

    secret = secrets.token_urlsafe(32)
    config = WebhookConfig(
        tenant_id=tenant_id,
        source=req.source,
        secret=secret,
        auto_scan=req.auto_scan,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)

    return {
        "id": config.id,
        "message": f"Webhook configured for {req.source}",
        "source": req.source,
        "secret": secret,
        "webhook_url": _build_webhook_url(req.source, tenant_slug, secret),
        "auto_scan": req.auto_scan,
        "created_at": config.created_at.isoformat() if config.created_at else None,
    }


@router.get("")
async def list_webhook_configs(current: dict = Depends(get_current_tenant)):
    db: AsyncSession = current["db"]
    tenant_id = current["tenant_id"]
    tenant_slug = current["tenant"].slug

    result = await db.execute(
        select(WebhookConfig).where(WebhookConfig.tenant_id == tenant_id)
    )
    configs = result.scalars().all()

    return {
        "configs": [
            {
                "id": c.id,
                "source": c.source,
                "secret": c.secret,
                "auto_scan": c.auto_scan,
                "webhook_url": _build_webhook_url(c.source, tenant_slug, c.secret),
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in configs
        ]
    }


@router.delete("/{config_id}")
async def delete_webhook_config(config_id: str, current: dict = Depends(get_current_tenant)):
    if current["role"] not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can delete webhook configs")

    db: AsyncSession = current["db"]
    tenant_id = current["tenant_id"]

    result = await db.execute(
        select(WebhookConfig).where(
            WebhookConfig.id == config_id,
            WebhookConfig.tenant_id == tenant_id,
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Webhook config not found")

    await db.delete(config)
    await db.commit()
    return {"message": "Webhook config deleted"}
