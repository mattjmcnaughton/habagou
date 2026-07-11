"""FastAPI dependencies shared by API routers."""

from typing import Annotated
from uuid import UUID

import structlog
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import (  # noqa: TC002 - FastAPI resolves annotations.
    AsyncSession,
)

from habagou.db import get_session
from habagou.events import emit_workflow_event
from habagou.models import (  # noqa: TC001 - FastAPI resolves annotations.
    User,
)


async def get_current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    """Resolve the authenticated user from the signed session cookie."""
    user = await get_optional_current_user(request, session)
    if user is not None:
        return user

    emit_workflow_event(
        "auth_gate_rejected",
        workflow="WF-AUTH-GATE",
        outcome="error",
        duration_ms=0,
        path=request.url.path,
    )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="authentication required",
    )


async def get_optional_current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User | None:
    """Resolve the signed-in user, clearing a stale or malformed session."""
    raw_user_id = request.session.get("user_id")
    if not raw_user_id:
        return None

    try:
        user_id = UUID(str(raw_user_id))
    except ValueError:
        request.session.clear()
        return None

    user = await session.get(User, user_id)
    if user is None:
        request.session.clear()
        return None

    _bind_user_to_request(request, user)
    return user


def _bind_user_to_request(request: Request, user: User) -> None:
    user_id = str(user.id)
    request.state.current_user_id = user_id
    structlog.contextvars.bind_contextvars(user_id=user_id)
