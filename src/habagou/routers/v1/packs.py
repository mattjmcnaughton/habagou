"""Pack API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import (  # noqa: TC002 - FastAPI resolves annotations.
    AsyncSession,
)

from habagou.db import get_session
from habagou.dependencies import get_current_user
from habagou.dtos.packs import PackDetailDTO, PackSummaryDTO
from habagou.events import workflow_event
from habagou.models import User  # noqa: TC001 - FastAPI resolves annotations.
from habagou.services.packs import PackService

router = APIRouter(prefix="/api/v1/packs", tags=["packs"])


@router.get("", response_model=list[PackSummaryDTO])
async def list_packs(
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[PackSummaryDTO]:
    async with workflow_event("pack_list_served", workflow="WF-02") as event:
        packs = await PackService(session).list_published(current_user)
        event.fields.update(pack_count=len(packs), user_id=str(current_user.id))
        return packs


@router.get(
    "/{slug}",
    response_model=PackDetailDTO,
    responses={404: {"description": "Pack not found"}},
)
async def get_pack(
    slug: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PackDetailDTO:
    async with workflow_event(
        "pack_served",
        workflow="WF-02",
        pack_slug=slug,
        user_id=str(current_user.id),
    ) as event:
        pack = await PackService(session).get_visible_by_slug(slug, current_user)
        if pack is None:
            event.outcome = "error"
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="pack not found",
            )

        return pack
