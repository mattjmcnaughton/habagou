"""Conversational practice API routes (WF-16, ADR 0011).

One tutor turn per request: learner message plus opaque client-held history
in, structured ``PracticeTurn`` plus updated history out. No persistence —
conversations are ephemeral and live entirely client-side.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError
from pydantic_ai import Agent  # noqa: TC002 - FastAPI resolves annotations.
from pydantic_ai.exceptions import ModelAPIError, UnexpectedModelBehavior

from habagou.config import settings
from habagou.dependencies import get_current_user

# PracticeTurn parameterizes the injected Agent annotation, which FastAPI
# resolves at runtime, so it is imported eagerly (not TYPE_CHECKING).
from habagou.dtos.practice import (
    PracticeStatusDTO,
    PracticeTurn,  # noqa: TC001 - parameterizes a FastAPI-resolved annotation.
    PracticeTurnRequestDTO,
    PracticeTurnResponseDTO,
)
from habagou.events import workflow_event
from habagou.models import User  # noqa: TC001 - FastAPI resolves annotations.
from habagou.routers.v1.chat_models import admin_model_options, resolve_model_override
from habagou.services.message_history import (
    dump_message_history,
    load_message_history,
)
from habagou.services.practice_chat import (
    PracticeNotConfiguredError,
    get_practice_agent,
    run_practice_turn,
)
from habagou.services.rate_limit import (  # noqa: TC001 - FastAPI resolves annotations.
    FixedWindowRateLimiter,
)

router = APIRouter(prefix="/api/v1/practice", tags=["practice"])


def get_practice_rate_limiter(request: Request) -> FixedWindowRateLimiter:
    """Return the per-app practice-turn rate limiter created in ``create_app``.

    Held on ``app.state`` (not a module global) so every app instance — and
    thus every test — gets a fresh limiter with no shared window state. A
    separate instance from the generation limiter: the two features have
    independent caps.
    """
    limiter: FixedWindowRateLimiter = request.app.state.practice_rate_limiter
    return limiter


@router.get("/status", response_model=PracticeStatusDTO)
async def get_practice_status(
    current_user: Annotated[User, Depends(get_current_user)],
) -> PracticeStatusDTO:
    """Report whether conversational practice is available, for UI gating.

    The Practice tab always renders; the practice screen calls this to decide
    between the topic picker and an unavailable state, so a user is never
    routed into a flow the ``/turn`` endpoint can only 503. Deliberately
    cheap, mirroring ``GET /api/v1/generation/status``: a stateless readiness
    probe over a config flag — no rate limiting, no workflow event.

    For admin callers (and only when practice is configured) the response also
    carries the selectable models and the server default, which is what
    renders the model picker — ``models`` stays ``None`` for everyone else.
    """
    models = admin_model_options(
        current_user,
        configured=settings.practice_configured,
        model_ids=settings.practice_model_ids,
    )
    return PracticeStatusDTO(
        enabled=settings.practice_configured,
        models=models,
        default_model=settings.practice_model if models is not None else None,
    )


@router.post(
    "/turn",
    response_model=PracticeTurnResponseDTO,
    responses={
        403: {"description": "Model selection requires an admin account"},
        422: {"description": "Requested model is not selectable"},
        429: {"description": "Per-user practice rate limit exceeded"},
        502: {"description": "Practice turn failed"},
        503: {"description": "Conversational practice is not configured"},
    },
)
async def practice_turn(
    payload: PracticeTurnRequestDTO,
    agent: Annotated[Agent[None, PracticeTurn], Depends(get_practice_agent)],
    current_user: Annotated[User, Depends(get_current_user)],
    limiter: Annotated[FixedWindowRateLimiter, Depends(get_practice_rate_limiter)],
) -> PracticeTurnResponseDTO:
    """Run one tutor turn for the caller's message (or opening topic)."""
    async with workflow_event(
        "practice_turn_completed",
        workflow="WF-16",
        user_id=str(current_user.id),
    ) as event:
        # Count every authenticated attempt before the (billed) model call, so
        # a caller cannot exceed their hourly quota by triggering repeated
        # failures; see ``services.rate_limit``.
        if not limiter.acquire(str(current_user.id)):
            event.outcome = "error"
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="practice rate limit exceeded; try again later",
            )
        try:
            history = (
                load_message_history(payload.history)
                if payload.history is not None
                else None
            )
        except ValidationError as exc:
            # The client-held history is opaque JSON; a corrupted or
            # hand-crafted payload is the caller's error, not a server fault.
            event.outcome = "error"
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="history is not a valid practice message history",
            ) from exc
        try:
            # Admin-only model override (403 for non-admins, 422 off-allowlist).
            model_id = resolve_model_override(
                payload.model,
                user=current_user,
                allowed=settings.practice_model_ids,
            )
        except HTTPException:
            event.outcome = "error"
            raise
        try:
            result = await run_practice_turn(
                agent,
                message=payload.message,
                history=history,
                model_id=model_id,
            )
        except PracticeNotConfiguredError as exc:
            event.outcome = "error"
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="conversational practice is not configured",
            ) from exc
        except (UnexpectedModelBehavior, ModelAPIError) as exc:
            # ModelAPIError covers provider HTTP errors and connection/timeout
            # failures alike (ModelHTTPError is its subclass).
            event.outcome = "error"
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="practice turn failed",
            ) from exc

        event.fields.update(
            segment_count=len(result.turn.segments),
            model=model_id or settings.practice_model,
        )
        return PracticeTurnResponseDTO(
            turn=result.turn,
            history=dump_message_history(result.messages),
        )
