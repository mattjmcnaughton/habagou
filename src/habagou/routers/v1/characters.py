"""Character stroke-data API routes."""

import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import (  # noqa: TC002 - FastAPI resolves annotations.
    AsyncSession,
)

from habagou.db import get_session
from habagou.events import emit_workflow_event
from habagou.repositories import CharacterRepository

router = APIRouter(prefix="/api/v1/characters", tags=["characters"])

CACHE_CONTROL_IMMUTABLE = "public, max-age=31536000, immutable"


@router.get(
    "/{hanzi}/strokes",
    responses={
        200: {"description": "Hanzi Writer stroke JSON"},
        404: {"description": "Character stroke data not found"},
        422: {"description": "Path parameter must be exactly one grapheme"},
    },
)
async def get_character_strokes(
    hanzi: str,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    started_at = time.perf_counter()
    if len(hanzi) != 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="hanzi must be exactly one grapheme",
        )

    stroke_data = await CharacterRepository(session).strokes_by_hanzi(hanzi)
    if stroke_data is None:
        emit_workflow_event(
            "strokes_missing",
            workflow="WF-06",
            outcome="error",
            duration_ms=_elapsed_ms(started_at),
            hanzi=hanzi,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="stroke data not found",
        )

    response.headers["Cache-Control"] = CACHE_CONTROL_IMMUTABLE
    emit_workflow_event(
        "strokes_served",
        workflow="WF-06",
        duration_ms=_elapsed_ms(started_at),
        hanzi=hanzi,
        found=True,
    )
    return stroke_data


def _elapsed_ms(started_at: float) -> int:
    return round((time.perf_counter() - started_at) * 1000)
