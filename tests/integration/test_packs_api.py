from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import func, select

from habagou import db
from habagou.app import create_app
from habagou.models import (
    ActivityCompletion,
    ActivityType,
    Pack,
    User,
)
from tests.integration.conftest import (
    auth_cookies,
    create_user,
    pack_by_slug,
    pack_id_by_slug,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncSession


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
    assert [pack["title"] for pack in body] == [
        "Greetings",
        "Numbers",
        "Family",
        "Food & drink",
    ]
    assert body[0] == {
        "id": body[0]["id"],
        "title": "Greetings",
        "glyph": "你",
        "color": "#c4633f",
        "char_count": 5,
        "sentence_count": 3,
        "owned": False,
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

    greetings_id = await pack_id_by_slug("greetings")
    response = await client.get(f"/api/v1/packs/{greetings_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Greetings"
    assert body["char_count"] == 5
    assert body["sentence_count"] == 3
    assert body["owned"] is False
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
    assert events[0][1]["pack_id"] == str(greetings_id)
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
    foreign_id = await _create_owned_pack("foreign-pack", owner_id=other_id)
    unknown_id = uuid.uuid4()
    events: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        "habagou.events.emit_workflow_event",
        lambda event, **fields: events.append((event, fields)),
    )

    unknown_response = await client.get(f"/api/v1/packs/{unknown_id}")
    foreign_response = await client.get(f"/api/v1/packs/{foreign_id}")
    assert unknown_response.status_code == 404
    assert foreign_response.status_code == 404
    # An unknown id and a foreign-owned id are indistinguishable to the caller:
    # the 404 code and message match (only the per-request request_id differs),
    # so pack existence never leaks.
    assert _error_without_request_id(unknown_response) == _error_without_request_id(
        foreign_response
    )
    assert [event for event, _fields in events] == ["pack_served", "pack_served"]
    assert [fields["outcome"] for _event, fields in events] == ["error", "error"]


@pytest.mark.workflow("WF-02")
@pytest.mark.anyio
async def test_get_pack_422s_on_malformed_id(client: AsyncClient) -> None:
    # A non-UUID path segment is rejected by FastAPI before the route runs.
    response = await client.get("/api/v1/packs/not-a-uuid")

    assert response.status_code == 422


@pytest.mark.workflow("WF-02")
@pytest.mark.anyio
async def test_list_packs_includes_own_excludes_foreign_owned(
    client: AsyncClient,
    current_user: User,
) -> None:
    async with db.async_session() as session:
        other = await create_user(session, username="other-owner", email=None)
        await session.commit()
        other_id = other.id
    mine_id = await _create_owned_pack("mine-cat", owner_id=current_user.id)
    foreign_id = await _create_owned_pack("foreign-cat", owner_id=other_id)

    response = await client.get("/api/v1/packs")

    assert response.status_code == 200
    body = response.json()
    ids = {pack["id"] for pack in body}
    assert str(mine_id) in ids
    assert str(foreign_id) not in ids
    titles = {pack["title"] for pack in body}
    assert {"Greetings", "Numbers", "Family", "Food & drink"} <= titles
    owned_by_id = {pack["id"]: pack["owned"] for pack in body}
    assert owned_by_id[str(mine_id)] is True
    # Global curated packs are never owned by the caller.
    assert all(pack["owned"] is False for pack in body if pack["id"] != str(mine_id))


@pytest.mark.workflow("WF-02")
@pytest.mark.anyio
async def test_get_pack_returns_own_owned_pack(
    client: AsyncClient,
    current_user: User,
) -> None:
    my_pack_id = await _create_owned_pack("my-pack", owner_id=current_user.id)

    response = await client.get(f"/api/v1/packs/{my_pack_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(my_pack_id)
    assert body["owned"] is True


@pytest.mark.workflow("WF-02")
@pytest.mark.anyio
async def test_delete_own_pack_removes_pack_and_cascades_completions(
    client: AsyncClient,
    current_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    my_pack_id = await _create_owned_pack("del-mine", owner_id=current_user.id)
    await _record_completion(current_user.id, "del-mine", ActivityType.TRACE, 900)
    events: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        "habagou.events.emit_workflow_event",
        lambda event, **fields: events.append((event, fields)),
    )

    delete_response = await client.delete(f"/api/v1/packs/{my_pack_id}")

    assert delete_response.status_code == 204
    # The pack is gone: a follow-up fetch 404s and it drops out of the listing.
    assert (await client.get(f"/api/v1/packs/{my_pack_id}")).status_code == 404
    listed = {pack["id"] for pack in (await client.get("/api/v1/packs")).json()}
    assert str(my_pack_id) not in listed
    # The database cascade removed the user's completions for the pack.
    async with db.async_session() as session:
        assert await _completion_count(session, my_pack_id) == 0
    assert events[0][0] == "pack_deleted"
    assert events[0][1]["workflow"] == "WF-02"
    assert events[0][1]["pack_id"] == str(my_pack_id)
    assert events[0][1]["outcome"] == "ok"


@pytest.mark.workflow("WF-02")
@pytest.mark.anyio
async def test_delete_global_pack_is_forbidden(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    greetings_id = await pack_id_by_slug("greetings")
    events: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        "habagou.events.emit_workflow_event",
        lambda event, **fields: events.append((event, fields)),
    )

    response = await client.delete(f"/api/v1/packs/{greetings_id}")

    assert response.status_code == 403
    # A curated pack is only visible, never owned, so it survives the attempt.
    assert (await client.get(f"/api/v1/packs/{greetings_id}")).status_code == 200
    assert events[0][0] == "pack_deleted"
    assert events[0][1]["outcome"] == "error"


@pytest.mark.workflow("WF-02")
@pytest.mark.anyio
async def test_delete_foreign_owned_pack_404s(
    client: AsyncClient,
) -> None:
    async with db.async_session() as session:
        other = await create_user(session, username="other-owner", email=None)
        await session.commit()
        other_id = other.id
    foreign_id = await _create_owned_pack("del-foreign", owner_id=other_id)

    response = await client.delete(f"/api/v1/packs/{foreign_id}")

    assert response.status_code == 404
    # The foreign pack is untouched.
    async with db.async_session() as session:
        assert await session.get(Pack, foreign_id) is not None


@pytest.mark.workflow("WF-02")
@pytest.mark.anyio
async def test_delete_unknown_pack_404s(client: AsyncClient) -> None:
    response = await client.delete(f"/api/v1/packs/{uuid.uuid4()}")

    assert response.status_code == 404


@pytest.mark.anyio
async def test_packs_require_authentication() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        list_response = await client.get("/api/v1/packs")
        delete_response = await client.delete(f"/api/v1/packs/{uuid.uuid4()}")

    assert list_response.status_code == 401
    assert list_response.json()["error"]["code"] == "unauthenticated"
    assert delete_response.status_code == 401
    assert delete_response.json()["error"]["code"] == "unauthenticated"


def _error_without_request_id(response: Response) -> dict[str, object]:
    error = dict(response.json()["error"])
    error.pop("request_id", None)
    return error


async def _record_completion(
    user_id: object, slug: str, activity: ActivityType, duration_ms: int
) -> None:
    async with db.async_session() as session:
        pack = await pack_by_slug(session, slug)
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


async def _completion_count(session: AsyncSession, pack_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(ActivityCompletion)
        .where(ActivityCompletion.pack_id == pack_id)
    )
    return int(result.scalar_one())


async def _create_owned_pack(slug: str, *, owner_id: uuid.UUID) -> uuid.UUID:
    async with db.async_session() as session:
        pack = Pack(
            slug=slug,
            title="Owned",
            glyph="私",
            color="#000000",
            sort_order=99,
            owner_id=owner_id,
        )
        session.add(pack)
        await session.commit()
        return pack.id
