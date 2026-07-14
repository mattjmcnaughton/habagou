"""Agent pack-generation API routes (Epic 7).

Draft/refine a Chinese-character practice pack from a topic (HAB-083) and save a
finalized draft as an owned pack (HAB-084). The model is grounded against the
stroke corpus through the generation agent's tool + output validator; every
glyph in a saved pack is corpus-validated again at the repository layer.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic_ai import Agent  # noqa: TC002 - FastAPI resolves annotations.
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior
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

router = APIRouter(prefix="/api/v1/generation", tags=["generation"])


@router.post(
    "/draft",
    response_model=GenerationDraftResponseDTO,
    responses={
        502: {"description": "Pack generation failed"},
        503: {"description": "Pack generation is not configured"},
    },
)
async def generate_draft(
    payload: GenerationDraftRequestDTO,
    session: Annotated[AsyncSession, Depends(get_session)],
    agent: Annotated[Agent[GenerationDeps, PackDraft], Depends(get_generation_agent)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> GenerationDraftResponseDTO:
    """Draft (or refine) a corpus-grounded pack for the caller's topic."""
    # NOTE(WF-15): a `pack_draft_generated` workflow event is deferred to the
    # next batch, which registers WF-15 in workflows.yml. Emitting a WF-15
    # literal here now would break the event-catalog coverage test
    # (tests/unit/test_events.py); this endpoint is the seam for it.
    history = (
        load_message_history(payload.history) if payload.history is not None else None
    )
    try:
        result = await generate_pack_draft(
            agent,
            session=session,
            topic=payload.topic,
            history=history,
        )
    except GenerationNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="pack generation is not configured",
        ) from exc
    except (UnexpectedModelBehavior, ModelHTTPError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="pack generation failed",
        ) from exc

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
    try:
        pack = await save_pack_draft(
            session, draft=payload.draft, owner_id=current_user.id
        )
    except ValueError as exc:
        # Grounding layer 3 (repository) rejected a non-corpus glyph.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    detail = await PackService(session).get_visible(pack.id, current_user)
    # Just created and owned by the caller, so it is always visible.
    assert detail is not None
    return detail
