"""Health check endpoints."""

import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from habagou.errors import error_response
from habagou.events import emit_workflow_event

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict:
    """Liveness probe."""
    return {"status": "ok"}


@router.get("/readyz", response_model=None)
async def readyz(request: Request) -> dict[str, str] | JSONResponse:
    """Readiness probe."""
    from sqlalchemy import text

    from habagou import db

    started_at = time.perf_counter()
    try:
        async with db.async_session() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        emit_workflow_event(
            "deploy_ready",
            workflow="WF-10",
            outcome="error",
            duration_ms=_elapsed_ms(started_at),
            database="unreachable",
        )
        return error_response(
            request,
            status_code=503,
            code="database_unavailable",
            message="database is unreachable",
            details={"database": "unreachable"},
        )
    emit_workflow_event(
        "deploy_ready",
        workflow="WF-10",
        duration_ms=_elapsed_ms(started_at),
        database="reachable",
    )
    return {"status": "ready"}


def _elapsed_ms(started_at: float) -> int:
    return round((time.perf_counter() - started_at) * 1000)
