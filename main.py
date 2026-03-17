from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.scan import router as scan_router
from app.api.connectors import router as connectors_router
from app.core.config import settings

app = FastAPI(
    title="RepoRat",
    description="AI-powered repo scanner. Finds bugs before your users do.",
    version="0.1.0",
)

origins = [o.strip() for o in settings.cors_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(scan_router)
app.include_router(connectors_router)


@app.get("/")
async def root():
    return {"name": "RepoRat", "version": "0.1.0", "docs": "/docs"}


@app.get("/health")
async def health():
    return {"status": "ok"}
