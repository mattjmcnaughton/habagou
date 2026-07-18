"""Pack API routes."""

import uuid
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
from habagou.services.packs import PackDeletion, PackService

router = APIRouter(prefix="/api/v1/packs", tags=["packs"])


@router.get("", response_model=list[PackSummaryDTO])
async def list_packs(
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[PackSummaryDTO]:
    async with workflow_event("pack_list_served", workflow="WF-02") as event:
        packs = await PackService(session).list_visible(current_user)
        event.fields.update(pack_count=len(packs), user_id=str(current_user.id))
        return packs


@router.get(
    "/{pack_id}",
    response_model=PackDetailDTO,
    responses={404: {"description": "Pack not found"}},
)
async def get_pack(
    pack_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PackDetailDTO:
    async with workflow_event(
        "pack_served",
        workflow="WF-02",
        pack_id=str(pack_id),
        user_id=str(current_user.id),
    ) as event:
        pack = await PackService(session).get_visible(pack_id, current_user)
        if pack is None:
            event.outcome = "error"
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="pack not found",
            )

        return pack


@router.delete(
    "/{pack_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        403: {"description": "Cannot delete a curated pack"},
        404: {"description": "Pack not found"},
    },
)
async def delete_pack(
    pack_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    async with workflow_event(
        "pack_deleted",
        workflow="WF-02",
        pack_id=str(pack_id),
        user_id=str(current_user.id),
    ) as event:
        outcome = await PackService(session).delete(pack_id, current_user)
        if outcome is PackDeletion.NOT_FOUND:
            event.outcome = "error"
            event.fields["reason"] = "pack_not_found"
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="pack not found",
            )
        if outcome is PackDeletion.FORBIDDEN:
            event.outcome = "error"
            event.fields["reason"] = "curated_pack"
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="cannot delete a curated pack",
            )
