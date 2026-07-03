"""FastAPI application factory."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from habagou.logging import configure_logging
from habagou.routers import health
from habagou.routers.v1 import characters, packs
from habagou.telemetry import setup_telemetry
from habagou.web.serve import mount_frontend

DESCRIPTION = "Learn to write Chinese characters by tracing them, stroke by stroke."


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    configure_logging()
    yield


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="habagou",
        description=DESCRIPTION,
        version="0.1.0",
        lifespan=lifespan,
    )

    setup_telemetry(app)

    app.include_router(health.router)
    app.include_router(characters.router)
    app.include_router(packs.router)

    # Mount frontend static files (only serves if dist/ exists)
    mount_frontend(app)

    return app


app = create_app()
