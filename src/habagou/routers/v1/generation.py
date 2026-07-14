"""Agent pack-generation API routes (Epic 7).

Draft/refine a Chinese-character practice pack from a topic (HAB-083) and save a
finalized draft as an owned pack (HAB-084). The model is grounded against the
stroke corpus through the generation agent's tool + output validator; every
glyph in a saved pack is corpus-validated again at the repository layer.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError
from pydantic_ai import Agent  # noqa: TC002 - FastAPI resolves annotations.
from pydantic_ai.exceptions import ModelAPIError, UnexpectedModelBehavior
from sqlalchemy.ext.asyncio import (  # noqa: TC002 - FastAPI resolves annotations.
    AsyncSession,
)

from habagou.db import get_session
from habagou.dependencies import get_current_user

# PackDraft/GenerationDeps parameterize the injected Agent annotation, which
# FastAPI resolves at runtime, so they are imported eagerly (not TYPE_CHECKING).
from habagou.dtos.generation import (
    GenerationDraftRequestDTO,
    GenerationDraftResponseDTO,
    GenerationSavePackRequestDTO,
    PackDraft,  # noqa: TC001 - parameterizes a FastAPI-resolved annotation.
)
from habagou.dtos.packs import PackDetailDTO
from habagou.events import workflow_event
from habagou.models import User  # noqa: TC001 - FastAPI resolves annotations.
from habagou.services.pack_generation import (
    GenerationDeps,  # noqa: TC001 - parameterizes a FastAPI-resolved annotation.
    GenerationNotConfiguredError,
    dump_message_history,
    generate_pack_draft,
    get_generation_agent,
    load_message_history,
    save_pack_draft,
)
from habagou.services.packs import PackService
from habagou.services.rate_limit import (  # noqa: TC001 - FastAPI resolves annotations.
    FixedWindowRateLimiter,
)

router = APIRouter(prefix="/api/v1/generation", tags=["generation"])


def get_generation_rate_limiter(request: Request) -> FixedWindowRateLimiter:
    """Return the per-app draft rate limiter created in ``create_app``.

    Held on ``app.state`` (not a module global) so every app instance — and thus
    every test — gets a fresh limiter with no shared window state.
    """
    limiter: FixedWindowRateLimiter = request.app.state.generation_rate_limiter
    return limiter


@router.post(
    "/draft",
    response_model=GenerationDraftResponseDTO,
    responses={
        429: {"description": "Per-user generation rate limit exceeded"},
        502: {"description": "Pack generation failed"},
        503: {"description": "Pack generation is not configured"},
    },
)
async def generate_draft(
    payload: GenerationDraftRequestDTO,
    session: Annotated[AsyncSession, Depends(get_session)],
    agent: Annotated[Agent[GenerationDeps, PackDraft], Depends(get_generation_agent)],
    current_user: Annotated[User, Depends(get_current_user)],
    limiter: Annotated[FixedWindowRateLimiter, Depends(get_generation_rate_limiter)],
) -> GenerationDraftResponseDTO:
    """Draft (or refine) a corpus-grounded pack for the caller's topic."""
    async with workflow_event(
        "pack_draft_generated",
        workflow="WF-15",
        user_id=str(current_user.id),
    ) as event:
        # Count every authenticated draft attempt before the (billed) model
        # call, so a caller cannot exceed their hourly quota by triggering
        # repeated failures; see ``services.rate_limit``.
        if not limiter.acquire(str(current_user.id)):
            event.outcome = "error"
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="generation rate limit exceeded; try again later",
            )
        try:
            history = (
                load_message_history(payload.history)
                if payload.history is not None
                else None
            )
        except ValidationError as exc:
            # The client-held history is opaque JSON; a corrupted or hand-crafted
            # payload is the caller's error, not a server fault.
            event.outcome = "error"
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="history is not a valid generation message history",
            ) from exc
        try:
            result = await generate_pack_draft(
                agent,
                session=session,
                topic=payload.topic,
                history=history,
            )
        except GenerationNotConfiguredError as exc:
            event.outcome = "error"
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="pack generation is not configured",
            ) from exc
        except (UnexpectedModelBehavior, ModelAPIError) as exc:
            # ModelAPIError covers provider HTTP errors and connection/timeout
            # failures alike (ModelHTTPError is its subclass).
            event.outcome = "error"
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="pack generation failed",
            ) from exc

        event.fields.update(character_count=len(result.draft.characters))
        return GenerationDraftResponseDTO(
            draft=result.draft,
            history=dump_message_history(result.messages),
        )


@router.post(
    "/packs",
    response_model=PackDetailDTO,
    status_code=status.HTTP_201_CREATED,
    responses={422: {"description": "Draft references non-corpus characters"}},
)
async def save_pack(
    payload: GenerationSavePackRequestDTO,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PackDetailDTO:
    """Persist a finalized draft as a pack owned by the caller."""
    async with workflow_event(
        "generated_pack_saved",
        workflow="WF-15",
        user_id=str(current_user.id),
    ) as event:
        try:
            pack = await save_pack_draft(
                session, draft=payload.draft, owner_id=current_user.id
            )
        except ValueError as exc:
            # Grounding layer 3 (repository) rejected a non-corpus glyph.
            event.outcome = "error"
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc

        event.fields.update(pack_id=str(pack.id))
        detail = await PackService(session).get_visible(pack.id, current_user)
        # Just created and owned by the caller, so it is always visible.
        assert detail is not None
        return detail
