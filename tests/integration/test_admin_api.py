from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient

from habagou import db
from habagou.app import create_app
from habagou.config import settings
from tests.integration.conftest import auth_cookies, create_user

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    async with db.async_session() as session:
        user = await create_user(session)
        await session.commit()
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        client.cookies.update(auth_cookies(user.id))
        yield client


@pytest.mark.workflow("WF-09")
@pytest.mark.anyio
async def test_admin_endpoints_disabled_when_token_unset(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "admin_token", "")

    response = await client.post(
        "/api/v1/admin/packs/greetings/retire",
        headers={"ADMIN_TOKEN": "anything"},
    )

    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "service_unavailable",
        "message": "admin endpoints disabled: ADMIN_TOKEN is unset",
        "request_id": response.json()["error"]["request_id"],
    }


@pytest.mark.workflow("WF-09")
@pytest.mark.anyio
async def test_admin_endpoints_reject_missing_or_wrong_token(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "admin_token", "secret")
    events: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        "habagou.events.emit_workflow_event",
        lambda event, **fields: events.append((event, fields)),
    )

    missing = await client.post("/api/v1/admin/packs/greetings/retire")
    wrong = await client.post(
        "/api/v1/admin/packs/greetings/retire",
        headers={"ADMIN_TOKEN": "wrong"},
    )

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert [event for event, _fields in events] == ["admin_action", "admin_action"]
    assert [fields["authorized"] for _event, fields in events] == [False, False]
    assert [fields["reason"] for _event, fields in events] == [
        "unauthorized",
        "unauthorized",
    ]


@pytest.mark.workflow("WF-09")
@pytest.mark.anyio
async def test_admin_can_retire_publish_and_patch_sort_order(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "admin_token", "secret")
    events: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        "habagou.events.emit_workflow_event",
        lambda event, **fields: events.append((event, fields)),
    )

    retire = await client.post(
        "/api/v1/admin/packs/greetings/retire",
        headers={"ADMIN_TOKEN": "secret"},
    )
    retired_list = await client.get("/api/v1/packs")
    retired_detail = await client.get("/api/v1/packs/greetings")
    publish = await client.post(
        "/api/v1/admin/packs/greetings/publish",
        headers={"ADMIN_TOKEN": "secret"},
    )
    patch = await client.patch(
        "/api/v1/admin/packs/greetings",
        headers={"ADMIN_TOKEN": "secret"},
        json={"sort_order": 99},
    )
    published_list = await client.get("/api/v1/packs")

    assert retire.status_code == 200
    assert retire.json()["status"] == "retired"
    assert "greetings" not in [pack["slug"] for pack in retired_list.json()]
    assert retired_detail.status_code == 404
    assert publish.status_code == 200
    assert publish.json()["status"] == "published"
    assert patch.status_code == 200
    assert patch.json()["sort_order"] == 99
    assert [pack["slug"] for pack in published_list.json()][-1] == "greetings"
    admin_events = [
        (event, fields) for event, fields in events if event == "admin_action"
    ]
    assert [
        (event, fields["action"], fields["authorized"])
        for event, fields in admin_events
    ] == [
        ("admin_action", "retire", True),
        ("admin_action", "publish", True),
        ("admin_action", "patch_sort_order", True),
    ]
