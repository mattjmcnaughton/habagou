"""Agent pack-generation API routes (Epic 7).

Draft/refine a Chinese-character practice pack from a topic (HAB-083). The model
is grounded against the stroke corpus through the generation agent's tool +
output validator.
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
    PackDraft,  # noqa: TC001 - parameterizes a FastAPI-resolved annotation.
)
from habagou.models import User  # noqa: TC001 - FastAPI resolves annotations.
from habagou.services.pack_generation import (
    GenerationDeps,  # noqa: TC001 - parameterizes a FastAPI-resolved annotation.
    GenerationNotConfiguredError,
    dump_message_history,
    generate_pack_draft,
    get_generation_agent,
    load_message_history,
)

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
