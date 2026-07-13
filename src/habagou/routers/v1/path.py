"""Learning Path API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import (  # noqa: TC002 - FastAPI resolves annotations.
    AsyncSession,
)

from habagou.db import get_session
from habagou.dependencies import get_current_user
from habagou.dtos.path import (
    PathItemCompleteDTO,
    PathItemCompleteResponseDTO,
    PathResponseDTO,
)
from habagou.events import workflow_event
from habagou.models import User  # noqa: TC001 - FastAPI resolves annotations.
from habagou.services.path import PathService

router = APIRouter(prefix="/api/v1/path", tags=["path"])


@router.get("", response_model=PathResponseDTO)
async def get_path(
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    cursor: Annotated[int | None, Query(ge=0)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> PathResponseDTO:
    async with workflow_event("path_viewed", workflow="WF-12") as event:
        result = await PathService(session).get_path(
            user=current_user,
            cursor=cursor,
            limit=limit,
        )
        event.fields.update(
            user_id=str(current_user.id),
            item_count=len(result.items),
            due_new=result.due.new,
            due_review=result.due.review,
        )
        return result


@router.post(
    "/items/{item_id}/complete",
    response_model=PathItemCompleteResponseDTO,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"description": "Path item not found"},
        409: {"description": "Path item already completed"},
    },
)
async def complete_path_item(
    item_id: UUID,
    body: PathItemCompleteDTO,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PathItemCompleteResponseDTO:
    async with workflow_event(
        "path_item_completed",
        workflow="WF-13",
        user_id=str(current_user.id),
    ) as event:
        result = await PathService(session).complete_item(
            user=current_user,
            item_id=item_id,
            duration_ms=body.duration_ms,
        )
        if result.status == "not_found":
            event.outcome = "error"
            event.fields["reason"] = "item_not_found"
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"path item not found: {item_id}",
            )
        if result.status == "conflict":
            event.outcome = "error"
            event.fields["reason"] = "already_completed"
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"path item already completed: {item_id}",
            )

        # A completed review item is the observable signal for WF-14 (review
        # resurfacing); it shares the path_item_completed event (see
        # docs/verification.md).
        if result.kind == "review":
            event.workflow = "WF-14"
        event.duration_ms = body.duration_ms
        event.fields.update(
            activity=result.activity,
            pack_id=result.pack_id,
            kind=result.kind,
        )
        assert result.response is not None
        return result.response
