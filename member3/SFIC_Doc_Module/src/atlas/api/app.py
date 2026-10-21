"""FastAPI application instance for ATLAS Dev 3 evidence processing service.

Implements PLAN.md Section 4.7 and J4 specifications:
- Exposes REST endpoints for document upload, job management, results, review items,
  cross-case suggestions, graph generation, and provenance evidence inspection.
"""

from __future__ import annotations

from fastapi import FastAPI

from atlas.api.routes import router
from atlas.api.ui import router as ui_router
from atlas.version import PIPELINE_VERSION


def create_app() -> FastAPI:
    """Initialize and configure the ATLAS FastAPI application."""
    application = FastAPI(
        title="ATLAS Dev 3 Evidence Pipeline API",
        description="REST API for multi-format police document evidence extraction, entity resolution, and graph synthesis.",
        version=PIPELINE_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    application.include_router(router)
    application.include_router(ui_router)
    return application


app = create_app()

__all__ = ["app", "create_app"]
