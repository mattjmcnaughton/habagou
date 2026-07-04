"""API error response DTOs."""

from typing import Any

from pydantic import BaseModel, Field


class ErrorDetailDTO(BaseModel):
    """Canonical API error payload."""

    code: str
    message: str
    request_id: str
    details: Any | None = None


class ErrorEnvelopeDTO(BaseModel):
    """Top-level API error envelope."""

    error: ErrorDetailDTO = Field(..., description="Canonical API error details")
