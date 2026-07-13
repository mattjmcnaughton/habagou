from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import update

from habagou import db
from habagou.app import create_app
from habagou.models import ActivityType, PathItem, ReviewState, User
from habagou.repositories import (
    PackCharacterInput,
    PackRepository,
    PathRepository,
    ProgressRepository,
    ReviewStateRepository,
    UserRepository,
)
from habagou.services.path import PENDING_WINDOW, PathService
from tests.integration.conftest import auth_cookies, create_user, pack_by_title

if TYPE_CHECKING:
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


# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #
async def _get_path(client: AsyncClient, *, cursor: int | None = None, limit: int = 20):
    params: dict[str, int] = {"limit": limit}
    if cursor is not None:
        params["cursor"] = cursor
    response = await client.get("/api/v1/path", params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def _complete(client: AsyncClient, item_id: str, *, duration_ms: int = 41200):
    return await client.post(
        f"/api/v1/path/items/{item_id}/complete",
        json={"duration_ms": duration_ms},
    )


async def _all_path_items(user_id: uuid.UUID) -> list[PathItem]:
    async with db.async_session() as session:
        return await PathRepository(session).list_for_user(user_id=user_id)


async def _generate_for_new_user(username: str) -> tuple[uuid.UUID, uuid.UUID]:
    """Create a second learner, materialize their path, return (user_id, item_id)."""
    async with db.async_session() as session:
        user = await create_user(session, username=username)
        await session.commit()
        user_id = user.id
    async with db.async_session() as session:
        user = await session.get(User, user_id)
        assert user is not None
        await PathService(session).get_path(user=user)
        items = await PathRepository(session).list_for_user(user_id=user_id)
        return user_id, items[0].id


# --------------------------------------------------------------------------- #
# 0. Path is global-only: owned packs never enter the curriculum.
# --------------------------------------------------------------------------- #
@pytest.mark.workflow("WF-12")
@pytest.mark.anyio
async def test_path_excludes_owned_packs(
    client: AsyncClient,
    current_user: User,
) -> None:
    # An owned pack -- even the caller's own, with valid corpus characters --
    # must never be scheduled: the Path is sourced from global packs only.
    async with db.async_session() as session:
        await PackRepository(session).create(
            owner_id=current_user.id,
            slug="owned-path",
            title="Owned Path",
            glyph="私",
            color="#000000",
            sort_order=99,
            characters=[PackCharacterInput(hanzi="你", pinyin="nǐ", meaning="you")],
            sentences=[],
        )
        await session.commit()

    body = await _get_path(client, limit=50)

    titles = {item["pack"]["title"] for item in body["items"]}
    assert "Owned Path" not in titles


# --------------------------------------------------------------------------- #
# 1. Contract shape.
# --------------------------------------------------------------------------- #
@pytest.mark.workflow("WF-12")
@pytest.mark.anyio
async def test_first_get_materializes_queue_with_contract_shape(
    client: AsyncClient,
) -> None:
    body = await _get_path(client)

    assert set(body) == {"items", "next_cursor", "daily", "streak", "due"}
    assert body["daily"] == {"completed": 0, "target": 3}
    assert body["streak"] == 0

    items = body["items"]
    assert len(items) >= PENDING_WINDOW

    # State derivation: first item current, all the rest locked (none done yet).
    assert items[0]["state"] == "current"
    assert all(item["state"] == "locked" for item in items[1:])
    assert all(item["kind"] == "new" for item in items)

    # Unit label only on the batch head.
    assert items[0]["unit_label"] == "UNIT 1 · WARMING UP"
    assert items[1]["unit_label"] is None

    # due counts every pending item by kind (all pending, all new here).
    assert body["due"] == {"new": len(items), "review": 0}

    # content carries exactly one key matching the activity; pack badge present.
    for item in items:
        assert list(item["content"].keys()) == [item["activity"]]
        assert set(item["pack"]) == {"title", "glyph", "color"}
        payload = item["content"][item["activity"]]
        if item["activity"] == "trace":
            assert payload["chars"] and "hanzi" in payload["chars"][0]
        elif item["activity"] == "match":
            assert payload["pairs"] and "hanzi" in payload["pairs"][0]
        else:
            assert {"hanzi", "pinyin", "translation"} <= set(payload)

    # Positions are strictly increasing.
    positions = [item["position"] for item in items]
    assert positions == sorted(positions)
    assert len(set(positions)) == len(positions)


# --------------------------------------------------------------------------- #
# 2. Pagination.
# --------------------------------------------------------------------------- #
@pytest.mark.workflow("WF-12")
@pytest.mark.anyio
async def test_cursor_pages_by_position(client: AsyncClient) -> None:
    first = await _get_path(client, limit=3)
    first_positions = [item["position"] for item in first["items"]]
    assert len(first_positions) == 3
    assert first["next_cursor"] == first_positions[-1]

    second = await _get_path(client, cursor=first["next_cursor"], limit=3)
    second_positions = [item["position"] for item in second["items"]]

    assert min(second_positions) > first["next_cursor"]
    assert second_positions == sorted(second_positions)
    assert not set(first_positions) & set(second_positions)
    assert second["next_cursor"] == second_positions[-1]


# --------------------------------------------------------------------------- #
# 3. Queue extension.
# --------------------------------------------------------------------------- #
@pytest.mark.workflow("WF-12")
@pytest.mark.workflow("WF-13")
@pytest.mark.anyio
async def test_queue_extends_when_pending_drops_below_window(
    current_user: User,
    client: AsyncClient,
) -> None:
    first = await _get_path(client)
    original = await _all_path_items(current_user.id)
    original_snapshot = {item.id: (item.position, item.content) for item in original}

    # Complete one item so pending drops below the window.
    complete = await _complete(client, first["items"][0]["id"])
    assert complete.status_code == 201

    await _get_path(client)
    extended = await _all_path_items(current_user.id)

    # New rows were appended; existing rows are untouched (append-only).
    assert len(extended) > len(original)
    for item in extended[: len(original)]:
        assert item.id in original_snapshot
        assert (item.position, item.content) == original_snapshot[item.id]

    positions = [item.position for item in extended]
    assert positions == sorted(positions)
    assert len(set(positions)) == len(positions)


@pytest.mark.workflow("WF-12")
@pytest.mark.workflow("WF-13")
@pytest.mark.anyio
async def test_concurrent_path_reads_extend_the_queue_once(
    current_user: User,
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_path = await _get_path(client)
    original = await _all_path_items(current_user.id)

    complete = await _complete(client, first_path["items"][0]["id"])
    assert complete.status_code == 201

    first_locked = asyncio.Event()
    second_started = asyncio.Event()
    release_first = asyncio.Event()
    lock_calls = 0
    original_lock = UserRepository.lock_by_id

    async def pause_first_lock(self: UserRepository, user_id: uuid.UUID) -> None:
        nonlocal lock_calls
        lock_calls += 1
        if lock_calls == 1:
            await original_lock(self, user_id)
            first_locked.set()
            await release_first.wait()
            return

        second_started.set()
        await original_lock(self, user_id)

    monkeypatch.setattr(UserRepository, "lock_by_id", pause_first_lock)
    transport = ASGITransport(app=create_app())
    async with (
        AsyncClient(transport=transport, base_url="http://testserver") as first_client,
        AsyncClient(transport=transport, base_url="http://testserver") as second_client,
    ):
        first_client.cookies.update(auth_cookies(current_user.id))
        second_client.cookies.update(auth_cookies(current_user.id))
        first_request = asyncio.create_task(first_client.get("/api/v1/path"))
        await first_locked.wait()

        second_request = asyncio.create_task(second_client.get("/api/v1/path"))
        await second_started.wait()
        release_first.set()
        first_response, second_response = await asyncio.gather(
            first_request, second_request
        )

    assert first_response.status_code == 200, first_response.text
    assert second_response.status_code == 200, second_response.text

    extended = await _all_path_items(current_user.id)
    positions = [item.position for item in extended]
    assert positions == sorted(positions)
    assert len(set(positions)) == len(positions)
    assert len(extended) > len(original)
    assert positions == [item["position"] for item in first_response.json()["items"]]


# --------------------------------------------------------------------------- #
# 4. Complete: shape, 409, 404.
# --------------------------------------------------------------------------- #
@pytest.mark.workflow("WF-13")
@pytest.mark.anyio
async def test_complete_item_shape_repeat_and_unknown(client: AsyncClient) -> None:
    body = await _get_path(client)
    current_id = body["items"][0]["id"]
    next_id = body["items"][1]["id"]

    response = await _complete(client, current_id, duration_ms=41200)
    assert response.status_code == 201
    payload = response.json()
    assert payload["item_id"] == current_id
    assert payload["next_item_id"] == next_id
    assert payload["daily"] == {"completed": 1, "target": 3}
    assert payload["streak"] == 0

    # Re-completing the same item is a conflict.
    repeat = await _complete(client, current_id)
    assert repeat.status_code == 409
    assert repeat.json()["error"]["code"] == "conflict"

    # Unknown id is a 404.
    unknown = await _complete(client, str(uuid.uuid4()))
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "not_found"

    # Another user's item is a 404 (never leaks across users).
    _, foreign_id = await _generate_for_new_user("foreign-user")
    foreign = await _complete(client, str(foreign_id))
    assert foreign.status_code == 404


# --------------------------------------------------------------------------- #
# 5. Projection rebuild == live table.
# --------------------------------------------------------------------------- #
@pytest.mark.workflow("WF-13")
@pytest.mark.anyio
async def test_review_state_projection_rebuilds_from_events(
    current_user: User,
    client: AsyncClient,
) -> None:
    body = await _get_path(client)
    # Complete a spread of items (trace / match / sentence) so several units
    # advance up the ladder.
    for item in body["items"][:5]:
        response = await _complete(client, item["id"])
        assert response.status_code == 201

    async with db.async_session() as session:
        rebuilt = await PathService(session).rebuild_review_states(
            user_id=current_user.id
        )
        live_rows = await ReviewStateRepository(session).list_for_user(
            user_id=current_user.id
        )

    live = {
        (row.pack_id, row.unit_type.value, row.unit_ref, row.activity.value): (
            row.reps,
            row.last_seen_at,
            row.due_at,
        )
        for row in live_rows
    }
    rebuilt_cmp = {
        key: (state.reps, state.last_seen_at, state.due_at)
        for key, state in rebuilt.items()
    }

    assert rebuilt_cmp == live
    # Sanity: at least one unit actually advanced and one stayed introduced-only.
    assert any(reps >= 1 for reps, _, _ in live.values())
    assert any(reps == 0 and due is None for reps, _, due in live.values())


# --------------------------------------------------------------------------- #
# 6. Due resurfacing (WF-14).
# --------------------------------------------------------------------------- #
@pytest.mark.workflow("WF-14")
@pytest.mark.anyio
async def test_due_unit_resurfaces_as_review_item(
    current_user: User,
    client: AsyncClient,
) -> None:
    body = await _get_path(client)
    trace_item = next(item for item in body["items"] if item["activity"] == "trace")
    traced_hanzi = {char["hanzi"] for char in trace_item["content"]["trace"]["chars"]}

    response = await _complete(client, trace_item["id"])
    assert response.status_code == 201

    max_position_before = max(
        item.position for item in await _all_path_items(current_user.id)
    )

    # Backdate the practised units so they are due.
    async with db.async_session() as session:
        await session.execute(
            update(ReviewState)
            .where(
                ReviewState.user_id == current_user.id,
                ReviewState.activity == ActivityType.TRACE,
                ReviewState.due_at.is_not(None),
            )
            .values(due_at=datetime.now(UTC) - timedelta(days=2))
        )
        await session.commit()

    resurfaced = await _get_path(client, limit=50)
    review_items = [
        item
        for item in resurfaced["items"]
        if item["kind"] == "review" and item["activity"] == "trace"
    ]
    assert review_items, "expected a resurfaced review item"

    review = review_items[0]
    review_hanzi = {char["hanzi"] for char in review["content"]["trace"]["chars"]}
    assert review_hanzi & traced_hanzi
    # Resurfaced review is appended at the tail (append-only queue).
    assert review["position"] > max_position_before
    assert resurfaced["due"]["review"] >= 1


# --------------------------------------------------------------------------- #
# 7. Path completions leave whole-pack badges untouched.
# --------------------------------------------------------------------------- #
@pytest.mark.workflow("WF-13")
@pytest.mark.anyio
async def test_path_completion_does_not_affect_pack_badges(
    current_user: User,
    client: AsyncClient,
) -> None:
    body = await _get_path(client)
    first = body["items"][0]
    pack_title = first["pack"]["title"]

    async with db.async_session() as session:
        pack = await pack_by_title(session, pack_title)
        assert pack is not None
        pack_id = pack.id
        before = await ProgressRepository(session).per_pack_aggregate(
            user_id=current_user.id, pack_id=pack_id
        )

    response = await _complete(client, first["id"])
    assert response.status_code == 201

    async with db.async_session() as session:
        after = await ProgressRepository(session).per_pack_aggregate(
            user_id=current_user.id, pack_id=pack_id
        )

    # Whole-pack aggregate (source='pack' only) is unchanged by a path lesson.
    assert {a: p.completed for a, p in before.items()} == {
        a: p.completed for a, p in after.items()
    }
    assert all(not p.completed for p in after.values())

    # Progress summary still works and reflects the path completion in the goal.
    summary = await client.get("/api/v1/progress/summary")
    assert summary.status_code == 200
    assert summary.json()["daily_goal"]["completed"] >= 1


@pytest.mark.anyio
async def test_path_requires_authentication() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/path")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"
