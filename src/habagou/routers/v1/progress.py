"""Progress API routes."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import (  # noqa: TC002 - FastAPI resolves annotations.
    AsyncSession,
)

from habagou.db import get_session
from habagou.dependencies import get_current_user
from habagou.dtos.progress import (
    CompletionCreateDTO,
    CompletionResponseDTO,
    PackProgressResponseDTO,
    ProgressResetDTO,
    ProgressSummaryDTO,
)
from habagou.events import workflow_event
from habagou.models import (  # noqa: TC001 - FastAPI resolves annotations.
    ActivityType,
    User,
)
from habagou.services.progress import ProgressService

router = APIRouter(prefix="/api/v1/progress", tags=["progress"])


@router.get("/summary", response_model=ProgressSummaryDTO)
async def get_progress_summary(
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    tz_offset_minutes: Annotated[int, Query(ge=-900, le=900)] = 0,
) -> ProgressSummaryDTO:
    async with workflow_event("progress_summary_viewed", workflow="WF-11") as event:
        result = await ProgressService(session).get_summary(
            user=current_user,
            tz_offset_minutes=tz_offset_minutes,
        )
        event.fields.update(
            user_id=str(current_user.id),
            current_streak=result.current_streak,
        )
        return result


@router.post(
    "/completions",
    response_model=CompletionResponseDTO,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"description": "Pack not found"}},
)
async def create_completion(
    completion: CompletionCreateDTO,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CompletionResponseDTO:
    async with workflow_event(
        "activity_completed",
        workflow=_workflow_for_activity(completion.activity),
        activity=completion.activity.value,
        pack_id=str(completion.pack_id),
        user_id=str(current_user.id),
    ) as event:
        result = await ProgressService(session).record_completion(
            user=current_user,
            completion=completion,
        )
        event.duration_ms = completion.duration_ms
        event.fields["request_duration_ms"] = event.elapsed_ms()
        if result is None:
            event.outcome = "error"
            event.fields["reason"] = "pack_not_found"
            raise _pack_not_found(completion.pack_id)

        return result


@router.get(
    "/packs/{pack_id}",
    response_model=PackProgressResponseDTO,
    responses={404: {"description": "Pack not found"}},
)
async def get_pack_progress(
    pack_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PackProgressResponseDTO:
    async with workflow_event(
        "progress_viewed",
        workflow="WF-07",
        pack_id=str(pack_id),
        user_id=str(current_user.id),
    ) as event:
        result = await ProgressService(session).get_pack_progress(
            user=current_user,
            pack_id=pack_id,
        )
        if result is None:
            event.outcome = "error"
            event.fields["reason"] = "pack_not_found"
            raise _pack_not_found(pack_id)
        return result


@router.delete(
    "/packs/{pack_id}",
    response_model=ProgressResetDTO,
    responses={404: {"description": "Pack not found"}},
)
async def reset_pack_progress(
    pack_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ProgressResetDTO:
    async with workflow_event(
        "progress_reset",
        workflow="WF-08",
        pack_id=str(pack_id),
        user_id=str(current_user.id),
    ) as event:
        result = await ProgressService(session).reset_pack_progress(
            user=current_user,
            pack_id=pack_id,
        )
        if result is None:
            event.outcome = "error"
            event.fields.update(deleted_count=0, reason="pack_not_found")
            raise _pack_not_found(pack_id)

        event.fields["deleted_count"] = result.deleted_count
        return result


def _pack_not_found(pack_id: uuid.UUID) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"pack not found: {pack_id}",
    )


def _workflow_for_activity(activity: ActivityType) -> str:
    match activity:
        case ActivityType.TRACE:
            return "WF-03"
        case ActivityType.MATCH:
            return "WF-04"
        case ActivityType.SENTENCE:
            return "WF-05"
