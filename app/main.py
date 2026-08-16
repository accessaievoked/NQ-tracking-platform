"""FastAPI application entrypoint."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import (
    analytics,
    auth,
    brands,
    integrations,
    live,
    reports,
    shopify_oauth,
)
from app.config import settings

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
app.include_router(analytics.router)
app.include_router(live.router)
# Public, key-authenticated pixel ingest — deliberately outside the session-auth
# brand routes above.
app.include_router(live.ingest_router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "env": settings.app_env}


# Serve the built React app (frontend/) as static files. Mounted last so the
# API routes and /health above take precedence; StaticFiles(html=True) serves
# index.html at "/" and falls through to it for unmatched paths.
_FRONTEND_DIST = Path(__file__).parent / "static"
if _FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=_FRONTEND_DIST, html=True), name="frontend")
