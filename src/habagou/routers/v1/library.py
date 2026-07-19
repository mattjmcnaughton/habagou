"""Pack library API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import (  # noqa: TC002 - FastAPI resolves annotations.
    AsyncSession,
)

from habagou.db import get_session
from habagou.dependencies import get_current_user
from habagou.dtos.packs import LibraryDTO
from habagou.events import workflow_event
from habagou.models import User  # noqa: TC001 - FastAPI resolves annotations.
from habagou.services.packs import PackService

router = APIRouter(prefix="/api/v1/library", tags=["library"])


@router.get("", response_model=LibraryDTO)
async def get_library(
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> LibraryDTO:
    async with workflow_event("library_served", workflow="WF-02") as event:
        library = await PackService(session).list_library(current_user)
        event.fields.update(
            category_count=len(library.categories),
            pack_count=sum(len(category.packs) for category in library.categories),
            user_id=str(current_user.id),
        )
        return library
