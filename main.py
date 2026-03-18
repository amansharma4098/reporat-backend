import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.scan import router as scan_router
from app.api.connectors import router as connectors_router
from app.api.auth import router as auth_router
from app.api.team import router as team_router
from app.api.webhooks import router as webhooks_router
from app.api.webhook_config import router as webhook_config_router
from app.api.notifications import router as notifications_router
from app.api.schedules import router as schedules_router
from app.core.config import settings
from app.core.database import create_tables
from app.services.scheduler import start_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    scheduler_task = asyncio.create_task(start_scheduler())
    yield
    scheduler_task.cancel()


app = FastAPI(
    title="RepoRat",
    description="AI-powered repo scanner. Finds bugs before your users do.",
    version="0.1.0",
    lifespan=lifespan,
)

# Always include these origins + whatever CORS_ORIGINS env provides
_hardcoded_origins = [
    "https://reporat-frontend.amansharma4098.workers.dev",
    "http://localhost:3000",
]
_env_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
origins = list(dict.fromkeys(_hardcoded_origins + _env_origins))

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(scan_router)
app.include_router(connectors_router)
app.include_router(team_router)
app.include_router(webhooks_router)
app.include_router(webhook_config_router)
app.include_router(notifications_router)
app.include_router(schedules_router)


@app.get("/")
async def root():
    return {"name": "RepoRat", "version": "0.1.0", "docs": "/docs"}


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
