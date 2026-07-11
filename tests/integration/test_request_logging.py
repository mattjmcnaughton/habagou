from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from httpx import ASGITransport, AsyncClient

from habagou import db
from habagou.app import create_app
from tests.integration.conftest import auth_cookies, create_user

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from habagou.models import User


@pytest.fixture
async def logged_client(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[tuple[AsyncClient, list[dict[str, Any]], User]]:
    async with db.async_session() as session:
        user = await create_user(session)
        await session.commit()

    logs: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "habagou.app.emit_request_log", lambda **fields: logs.append(fields)
    )
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        client.cookies.update(auth_cookies(user.id))
        yield client, logs, user


@pytest.mark.anyio
async def test_request_log_includes_resolved_user_id(
    logged_client: tuple[AsyncClient, list[dict[str, Any]], User],
) -> None:
    client, logs, user = logged_client
    response = await client.get("/api/v1/packs", headers={"X-Request-ID": "req-test"})

    assert response.status_code == 200
    assert logs[-1] == {
        "method": "GET",
        "path": "/api/v1/packs",
        "status_code": 200,
        "duration_ms": logs[-1]["duration_ms"],
        "request_id": "req-test",
        "user_id": str(user.id),
    }
    assert isinstance(logs[-1]["duration_ms"], int)
