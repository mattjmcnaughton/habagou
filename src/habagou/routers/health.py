"""Health check endpoints."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from habagou.errors import error_response
from habagou.events import workflow_event

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

    async with workflow_event("deploy_ready", workflow="WF-10") as event:
        try:
            async with db.async_session() as session:
                await session.execute(text("SELECT 1"))
        except Exception:
            event.outcome = "error"
            event.fields["database"] = "unreachable"
            return error_response(
                request,
                status_code=503,
                code="database_unavailable",
                message="database is unreachable",
                details={"database": "unreachable"},
            )

        event.fields["database"] = "reachable"
        return {"status": "ready"}
