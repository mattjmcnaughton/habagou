from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from habagou import db
from habagou.app import create_app
from habagou.models import (
    GUEST_USER_ID,
    ActivityCompletion,
    ActivityType,
    Pack,
    PackStatus,
    User,
)
from habagou.repositories import PackRepository

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.workflow("WF-02")
@pytest.mark.anyio
async def test_list_packs_returns_published_sorted_summaries(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _record_completion("greetings", ActivityType.MATCH, 1500)
    events: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        "habagou.routers.v1.packs.emit_workflow_event",
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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _record_completion("greetings", ActivityType.TRACE, 1200)
    await _record_completion("greetings", ActivityType.TRACE, 800)
    events: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        "habagou.routers.v1.packs.emit_workflow_event",
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
    assert "outcome" not in events[0][1]


@pytest.mark.workflow("WF-02")
@pytest.mark.anyio
async def test_get_pack_404s_for_unknown_or_unpublished(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _retire_pack("greetings")
    events: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        "habagou.routers.v1.packs.emit_workflow_event",
        lambda event, **fields: events.append((event, fields)),
    )

    assert (await client.get("/api/v1/packs/nope")).status_code == 404
    assert (await client.get("/api/v1/packs/greetings")).status_code == 404
    assert [event for event, _fields in events] == ["pack_served", "pack_served"]
    assert [fields["outcome"] for _event, fields in events] == ["error", "error"]


async def _record_completion(
    slug: str, activity: ActivityType, duration_ms: int
) -> None:
    async with db.async_session() as session:
        user = await session.get(User, GUEST_USER_ID)
        pack = await PackRepository(session).get_by_slug(slug)
        assert user is not None
        assert pack is not None
        session.add(
            ActivityCompletion(
                user_id=user.id,
                pack_id=pack.id,
                activity=activity,
                duration_ms=duration_ms,
            )
        )
        await session.commit()


async def _retire_pack(slug: str) -> None:
    async with db.async_session() as session:
        pack = await session.scalar(select(Pack).where(Pack.slug == slug))
        assert pack is not None
        pack.status = PackStatus.RETIRED
        await session.commit()
