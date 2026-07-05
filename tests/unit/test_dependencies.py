from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from habagou.dependencies import get_current_user
from habagou.models import GUEST_USER_ID, User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.anyio
async def test_get_current_user_returns_seeded_guest() -> None:
    guest = User(
        id=GUEST_USER_ID,
        username="guest",
        display_name="Guest",
        is_guest=True,
    )
    session_get_calls = 0

    class StubSession:
        async def get(self, model: type[User], ident: object) -> User:
            nonlocal session_get_calls
            session_get_calls += 1
            assert model is User
            assert ident == GUEST_USER_ID
            return guest

    session = cast("AsyncSession", StubSession())
    request = _request()
    assert await get_current_user(request, session) is guest
    assert await get_current_user(request, session) is guest
    assert request.state.current_user_id == str(GUEST_USER_ID)
    assert session_get_calls == 2


@pytest.mark.anyio
async def test_get_current_user_raises_when_guest_is_missing() -> None:
    class StubSession:
        async def get(self, model: type[User], ident: object) -> None:
            return None

    with pytest.raises(HTTPException) as error:
        await get_current_user(_request(), cast("AsyncSession", StubSession()))

    assert error.value.status_code == 503
    assert error.value.detail == "guest user is not seeded"


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": []})
