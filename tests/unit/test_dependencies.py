from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from fastapi import HTTPException

from habagou.dependencies import clear_current_user_cache, get_current_user
from habagou.models import User
from habagou.seed_data import GUEST_USER_ID

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    clear_current_user_cache()


@pytest.mark.anyio
async def test_get_current_user_returns_seeded_guest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guest = User(
        id=GUEST_USER_ID,
        username="guest",
        display_name="Guest",
        is_guest=True,
    )
    calls = 0
    session_get_calls = 0

    class StubUserRepository:
        def __init__(self, session: object) -> None:
            self.session = session

        async def get_guest(self) -> User:
            nonlocal calls
            calls += 1
            return guest

    class StubSession:
        async def get(self, model: type[User], ident: object) -> User:
            nonlocal session_get_calls
            session_get_calls += 1
            assert model is User
            assert ident == GUEST_USER_ID
            return guest

    monkeypatch.setattr("habagou.dependencies.UserRepository", StubUserRepository)

    session = cast("AsyncSession", StubSession())
    assert await get_current_user(session) is guest
    assert await get_current_user(session) is guest
    assert session_get_calls == 2
    assert calls == 0


@pytest.mark.anyio
async def test_get_current_user_raises_when_guest_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StubUserRepository:
        def __init__(self, session: object) -> None:
            self.session = session

        async def get_guest(self) -> None:
            return None

    class StubSession:
        async def get(self, model: type[User], ident: object) -> None:
            return None

    monkeypatch.setattr("habagou.dependencies.UserRepository", StubUserRepository)

    with pytest.raises(HTTPException) as error:
        await get_current_user(cast("AsyncSession", StubSession()))

    assert error.value.status_code == 503
