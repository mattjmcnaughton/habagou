from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, cast

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from habagou.dependencies import get_current_user, get_optional_current_user
from habagou.models import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.anyio
async def test_get_current_user_returns_session_user() -> None:
    user = User(
        id=uuid.UUID("11111111-1111-4111-8111-111111111111"),
        username="learner",
        display_name="Learner",
        is_guest=False,
    )
    session_get_calls = 0

    class StubSession:
        async def get(self, model: type[User], ident: object) -> User:
            nonlocal session_get_calls
            session_get_calls += 1
            assert model is User
            assert ident == user.id
            return user

    session = cast("AsyncSession", StubSession())
    request = _request({"user_id": str(user.id)})
    assert await get_current_user(request, session) is user
    assert await get_current_user(request, session) is user
    assert request.state.current_user_id == str(user.id)
    assert session_get_calls == 2


@pytest.mark.anyio
async def test_get_current_user_raises_when_session_user_is_missing() -> None:
    class StubSession:
        async def get(self, model: type[User], ident: object) -> None:
            return None

    with pytest.raises(HTTPException) as error:
        await get_current_user(
            _request({"user_id": "11111111-1111-4111-8111-111111111111"}),
            cast("AsyncSession", StubSession()),
        )

    assert error.value.status_code == 401
    assert error.value.detail == "authentication required"


@pytest.mark.anyio
async def test_optional_current_user_clears_a_stale_session() -> None:
    class StubSession:
        async def get(self, model: type[User], ident: object) -> None:
            return None

    request = _request({"user_id": "11111111-1111-4111-8111-111111111111"})

    assert (
        await get_optional_current_user(request, cast("AsyncSession", StubSession()))
    ) is None
    assert request.session == {}


@pytest.mark.anyio
async def test_get_current_user_raises_without_session_user() -> None:
    class StubSession:
        async def get(self, model: type[User], ident: object) -> None:
            raise AssertionError("database should not be queried")

    with pytest.raises(HTTPException) as error:
        await get_current_user(_request({}), cast("AsyncSession", StubSession()))

    assert error.value.status_code == 401
    assert error.value.detail == "authentication required"


def _request(session: dict[str, str]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "session": session,
        }
    )
