"""FastAPI dependencies shared by API routers."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import (  # noqa: TC002 - FastAPI resolves annotations.
    AsyncSession,
)

from habagou.db import get_session
from habagou.models import User  # noqa: TC001 - FastAPI resolves annotations.
from habagou.repositories import UserRepository
from habagou.seed_data import GUEST_USER_ID

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
