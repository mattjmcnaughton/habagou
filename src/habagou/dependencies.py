"""FastAPI dependencies shared by API routers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, HTTPException, status

from habagou.db import get_session
from habagou.models import User
from habagou.repositories import UserRepository
from habagou.seed_data import GUEST_USER_ID

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_guest_user_seeded = False


async def get_current_user(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    """Resolve the current user.

    v1 always maps requests to the seeded guest user. This is the single swap
    point for authenticated accounts later.
    """
    global _guest_user_seeded

    user = await session.get(User, GUEST_USER_ID)
    if user is not None:
        _guest_user_seeded = True
        return user

    if not _guest_user_seeded:
        user = await UserRepository(session).get_guest()
        if user is not None:
            _guest_user_seeded = True
            return user

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="guest user is not seeded",
        )

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="guest user is not available in this database",
    )


def clear_current_user_cache() -> None:
    """Clear the cached guest user for tests and database retargeting."""
    global _guest_user_seeded
    _guest_user_seeded = False
