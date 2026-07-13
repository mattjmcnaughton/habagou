"""FastAPI application factory."""

import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from habagou.auth import register_provider
from habagou.config import settings
from habagou.errors import error_response
from habagou.logging import configure_logging
from habagou.logging import log_request as emit_request_log
from habagou.routers import auth, health
from habagou.routers.v1 import characters, packs, path, progress
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
    _ensure_session_configured()
    register_provider(settings)
    app = FastAPI(
        title="habagou",
        description=DESCRIPTION,
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret_key,
        same_site="lax",
        https_only=settings.session_cookie_secure,
    )
    setup_telemetry(app)
    _install_request_logging(app)
    _install_error_handlers(app)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(characters.router)
    app.include_router(packs.router)
    app.include_router(path.router)
    app.include_router(progress.router)

    # Mount frontend static files (only serves if dist/ exists)
    mount_frontend(app)

    return app


def _ensure_session_configured() -> None:
    if not settings.session_secret_key:
        raise RuntimeError("SESSION_SECRET_KEY must be configured")


def _install_request_logging(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        structlog.contextvars.clear_contextvars()
        started_at = time.perf_counter()
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            emit_request_log(
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                duration_ms=round((time.perf_counter() - started_at) * 1000),
                request_id=request_id,
                user_id=getattr(request.state, "current_user_id", None),
            )
            structlog.contextvars.clear_contextvars()


def _install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        message = exc.detail if isinstance(exc.detail, str) else "request failed"
        return error_response(
            request,
            status_code=exc.status_code,
            code=_http_error_code(exc.status_code),
            message=message,
            details=None if isinstance(exc.detail, str) else exc.detail,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        return error_response(
            request,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="validation_error",
            message="request validation failed",
            details=exc.errors(),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, _exc: Exception):
        return error_response(
            request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_error",
            message="internal server error",
        )


def _http_error_code(status_code: int) -> str:
    return {
        401: "unauthenticated",
        404: "not_found",
        409: "conflict",
        422: "validation_error",
        503: "service_unavailable",
    }.get(status_code, f"http_{status_code}")


app = create_app()
