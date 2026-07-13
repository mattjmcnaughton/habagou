from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient

from habagou import db
from habagou.app import create_app
from habagou.models import (
    ActivityCompletion,
    ActivityType,
    Pack,
    PackStatus,
    User,
)
from habagou.repositories import PackRepository
from tests.integration.conftest import auth_cookies, create_user

if TYPE_CHECKING:
    import uuid
    from collections.abc import AsyncGenerator


@pytest.fixture
async def current_user() -> User:
    async with db.async_session() as session:
        user = await create_user(session)
        await session.commit()
        return user


@pytest.fixture
async def client(current_user: User) -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        client.cookies.update(auth_cookies(current_user.id))
        yield client


@pytest.mark.workflow("WF-02")
@pytest.mark.anyio
async def test_list_packs_returns_published_sorted_summaries(
    client: AsyncClient,
    current_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _record_completion(current_user.id, "greetings", ActivityType.MATCH, 1500)
    events: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        "habagou.events.emit_workflow_event",
        lambda event, **fields: events.append((event, fields)),
    )

    response = await client.get("/api/v1/packs")

    assert response.status_code == 200
    body = response.json()
    assert [pack["slug"] for pack in body] == [
        "greetings",
        "numbers",
        "family",
        "food-drink",
    ]
    assert body[0] == {
        "id": body[0]["id"],
        "slug": "greetings",
        "title": "Greetings",
        "glyph": "你",
        "color": "#c4633f",
        "char_count": 5,
        "sentence_count": 3,
        "progress": {
            "trace": {
                "completed": False,
                "completion_count": 0,
                "best_duration_ms": None,
            },
            "match": {
                "completed": True,
                "completion_count": 1,
                "best_duration_ms": 1500,
            },
            "sentence": {
                "completed": False,
                "completion_count": 0,
                "best_duration_ms": None,
            },
        },
    }
    assert events[0][0] == "pack_list_served"
    assert events[0][1]["workflow"] == "WF-02"
    assert events[0][1]["pack_count"] == 4


@pytest.mark.workflow("WF-02")
@pytest.mark.anyio
async def test_get_pack_returns_detail_with_progress(
    client: AsyncClient,
    current_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _record_completion(current_user.id, "greetings", ActivityType.TRACE, 1200)
    await _record_completion(current_user.id, "greetings", ActivityType.TRACE, 800)
    events: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        "habagou.events.emit_workflow_event",
        lambda event, **fields: events.append((event, fields)),
    )

    response = await client.get("/api/v1/packs/greetings")

    assert response.status_code == 200
    body = response.json()
    assert body["slug"] == "greetings"
    assert body["char_count"] == 5
    assert body["sentence_count"] == 3
    assert [character["hanzi"] for character in body["characters"]] == [
        "你",
        "好",
        "我",
        "他",
        "谢",
    ]
    assert [sentence["hanzi"] for sentence in body["sentences"]] == [
        "你好",
        "我很好",
        "谢谢你",
    ]
    assert body["progress"]["trace"] == {
        "completed": True,
        "completion_count": 2,
        "best_duration_ms": 800,
    }
    assert events[0][0] == "pack_served"
    assert events[0][1]["workflow"] == "WF-02"
    assert events[0][1]["pack_slug"] == "greetings"
    assert events[0][1]["outcome"] == "ok"


@pytest.mark.workflow("WF-02")
@pytest.mark.anyio
async def test_get_pack_404s_for_unknown_or_foreign_owned(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A foreign user's private pack is invisible even though it is published:
    # visibility is gated by ownership, not status.
    async with db.async_session() as session:
        other = await create_user(session, username="other-owner", email=None)
        await session.commit()
        other_id = other.id
    await _create_owned_pack("foreign-pack", owner_id=other_id)
    events: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        "habagou.events.emit_workflow_event",
        lambda event, **fields: events.append((event, fields)),
    )

    assert (await client.get("/api/v1/packs/nope")).status_code == 404
    assert (await client.get("/api/v1/packs/foreign-pack")).status_code == 404
    assert [event for event, _fields in events] == ["pack_served", "pack_served"]
    assert [fields["outcome"] for _event, fields in events] == ["error", "error"]


@pytest.mark.workflow("WF-02")
@pytest.mark.anyio
async def test_get_pack_returns_own_owned_pack(
    client: AsyncClient,
    current_user: User,
) -> None:
    await _create_owned_pack("my-pack", owner_id=current_user.id)

    response = await client.get("/api/v1/packs/my-pack")

    assert response.status_code == 200
    assert response.json()["slug"] == "my-pack"


@pytest.mark.anyio
async def test_packs_require_authentication() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/packs")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


async def _record_completion(
    user_id: object, slug: str, activity: ActivityType, duration_ms: int
) -> None:
    async with db.async_session() as session:
        pack = await PackRepository(session).get_by_slug(slug)
        assert pack is not None
        session.add(
            ActivityCompletion(
                user_id=user_id,
                pack_id=pack.id,
                activity=activity,
                duration_ms=duration_ms,
            )
        )
        await session.commit()


async def _create_owned_pack(slug: str, *, owner_id: uuid.UUID) -> None:
    async with db.async_session() as session:
        session.add(
            Pack(
                slug=slug,
                title="Owned",
                glyph="私",
                color="#000000",
                status=PackStatus.PUBLISHED,
                sort_order=99,
                owner_id=owner_id,
            )
        )
        await session.commit()
