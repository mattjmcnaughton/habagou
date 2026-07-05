"""FastAPI dependencies shared by API routers."""

from typing import Annotated

import structlog
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import (  # noqa: TC002 - FastAPI resolves annotations.
    AsyncSession,
)

from habagou.db import get_session
from habagou.models import (  # noqa: TC001 - FastAPI resolves annotations.
    GUEST_USER_ID,
    User,
)


async def get_current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    """Resolve the current user.

    v1 always maps requests to the seeded guest user. This is the single swap
    point for authenticated accounts later.
    """
    user = await session.get(User, GUEST_USER_ID)
    if user is not None:
        _bind_user_to_request(request, user)
        return user

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="guest user is not seeded",
    )


def _bind_user_to_request(request: Request, user: User) -> None:
    user_id = str(user.id)
    request.state.current_user_id = user_id
    structlog.contextvars.bind_contextvars(user_id=user_id)
