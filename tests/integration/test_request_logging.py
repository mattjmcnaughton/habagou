from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from httpx import ASGITransport, AsyncClient

from habagou.app import create_app
from habagou.seed_data import GUEST_USER_ID

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@pytest.fixture
async def logged_client(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[tuple[AsyncClient, list[dict[str, Any]]]]:
    logs: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "habagou.app.emit_request_log", lambda **fields: logs.append(fields)
    )
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client, logs


@pytest.mark.anyio
async def test_request_log_includes_resolved_user_id(
    logged_client: tuple[AsyncClient, list[dict[str, Any]]],
) -> None:
    client, logs = logged_client
    response = await client.get("/api/v1/packs", headers={"X-Request-ID": "req-test"})

    assert response.status_code == 200
    assert logs[-1] == {
        "method": "GET",
        "path": "/api/v1/packs",
        "status_code": 200,
        "duration_ms": logs[-1]["duration_ms"],
        "request_id": "req-test",
        "user_id": str(GUEST_USER_ID),
    }
    assert isinstance(logs[-1]["duration_ms"], int)
