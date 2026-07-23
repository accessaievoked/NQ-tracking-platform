"""FastAPI application entrypoint."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse

from app.api import auth, brands, integrations, reports, shopify_oauth
from app.config import settings

_WEB = Path(__file__).parent / "web"
_CONNECTIONS_PAGE = _WEB / "connections.html"
_APP_PAGE = _WEB / "app.html"

app = FastAPI(
    title="NQ Tracking Platform API",
    version="0.1.0",
    description="Backend for brand analytics workspaces and AI-generated reports.",
)

app.include_router(auth.router)
app.include_router(brands.router)
app.include_router(integrations.router)
app.include_router(shopify_oauth.router)
app.include_router(reports.router)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "env": settings.app_env}


@app.get("/connections", include_in_schema=False)
def connections_page():
    """Self-service connections UI (login + connect data sources)."""
    return FileResponse(_CONNECTIONS_PAGE)


@app.get("/app", include_in_schema=False)
def app_page():
    """NQ Brand Library web app (Figma design)."""
    return FileResponse(_APP_PAGE)
