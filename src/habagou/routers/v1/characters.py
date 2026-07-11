"""Character stroke-data API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import (  # noqa: TC002 - FastAPI resolves annotations.
    AsyncSession,
)

from habagou.db import get_session
from habagou.dependencies import get_current_user
from habagou.events import workflow_event
from habagou.repositories import CharacterRepository

router = APIRouter(
    prefix="/api/v1/characters",
    tags=["characters"],
    dependencies=[Depends(get_current_user)],
)

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
    async with workflow_event("strokes_served", workflow="WF-06", hanzi=hanzi) as event:
        if len(hanzi) != 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="hanzi must be exactly one grapheme",
            )

        stroke_data = await CharacterRepository(session).strokes_by_hanzi(hanzi)
        if stroke_data is None:
            event.event = "strokes_missing"
            event.outcome = "error"
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="stroke data not found",
            )

        response.headers["Cache-Control"] = CACHE_CONTROL_IMMUTABLE
        event.fields["found"] = True
        return stroke_data
