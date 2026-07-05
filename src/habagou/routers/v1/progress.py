"""Progress API routes."""

import time
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
from habagou.events import emit_workflow_event
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
    started_at = time.perf_counter()
    result = await ProgressService(session).get_summary(
        user=current_user,
        tz_offset_minutes=tz_offset_minutes,
    )
    emit_workflow_event(
        "progress_summary_viewed",
        workflow="WF-11",
        duration_ms=_elapsed_ms(started_at),
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
    started_at = time.perf_counter()
    result = await ProgressService(session).record_completion(
        user=current_user,
        completion=completion,
    )
    if result is None:
        emit_workflow_event(
            "activity_completed",
            workflow=_workflow_for_activity(completion.activity),
            outcome="error",
            duration_ms=completion.duration_ms,
            activity=completion.activity.value,
            pack_slug=completion.pack_slug,
            user_id=str(current_user.id),
            request_duration_ms=_elapsed_ms(started_at),
            reason="pack_not_found",
        )
        raise _pack_not_found(completion.pack_slug)

    emit_workflow_event(
        "activity_completed",
        workflow=_workflow_for_activity(completion.activity),
        duration_ms=completion.duration_ms,
        activity=completion.activity.value,
        pack_slug=completion.pack_slug,
        user_id=str(current_user.id),
        request_duration_ms=_elapsed_ms(started_at),
    )
    return result


@router.get(
    "/packs/{slug}",
    response_model=PackProgressResponseDTO,
    responses={404: {"description": "Pack not found"}},
)
async def get_pack_progress(
    slug: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PackProgressResponseDTO:
    started_at = time.perf_counter()
    result = await ProgressService(session).get_pack_progress(
        user=current_user,
        pack_slug=slug,
    )
    if result is None:
        emit_workflow_event(
            "progress_viewed",
            workflow="WF-07",
            outcome="error",
            duration_ms=_elapsed_ms(started_at),
            pack_slug=slug,
            user_id=str(current_user.id),
            reason="pack_not_found",
        )
        raise _pack_not_found(slug)
    emit_workflow_event(
        "progress_viewed",
        workflow="WF-07",
        duration_ms=_elapsed_ms(started_at),
        pack_slug=slug,
        user_id=str(current_user.id),
    )
    return result


@router.delete(
    "/packs/{slug}",
    response_model=ProgressResetDTO,
    responses={404: {"description": "Pack not found"}},
)
async def reset_pack_progress(
    slug: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ProgressResetDTO:
    started_at = time.perf_counter()
    result = await ProgressService(session).reset_pack_progress(
        user=current_user,
        pack_slug=slug,
    )
    if result is None:
        emit_workflow_event(
            "progress_reset",
            workflow="WF-08",
            outcome="error",
            duration_ms=_elapsed_ms(started_at),
            pack_slug=slug,
            deleted_count=0,
            user_id=str(current_user.id),
            reason="pack_not_found",
        )
        raise _pack_not_found(slug)

    emit_workflow_event(
        "progress_reset",
        workflow="WF-08",
        duration_ms=_elapsed_ms(started_at),
        pack_slug=slug,
        deleted_count=result.deleted_count,
        user_id=str(current_user.id),
    )
    return result


def _pack_not_found(slug: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"pack not found: {slug}",
    )


def _workflow_for_activity(activity: ActivityType) -> str:
    match activity:
        case ActivityType.TRACE:
            return "WF-03"
        case ActivityType.MATCH:
            return "WF-04"
        case ActivityType.SENTENCE:
            return "WF-05"


def _elapsed_ms(started_at: float) -> int:
    return round((time.perf_counter() - started_at) * 1000)
