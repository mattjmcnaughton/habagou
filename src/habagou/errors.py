"""Shared API error envelope helpers."""

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


def error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: Any | None = None,
) -> JSONResponse:
    """Build the canonical API error envelope."""
    request_id = getattr(request.state, "request_id", "")
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "request_id": request_id,
    }
    if details is not None:
        error["details"] = details
    content: dict[str, Any] = {
        "error": error,
    }
    return JSONResponse(content, status_code=status_code)
