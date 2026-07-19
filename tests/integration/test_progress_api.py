from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from habagou import db
from habagou.app import create_app
from habagou.models import ActivityCompletion, ActivityType, Pack, User
from habagou.repositories import PackRepository
from tests.integration.conftest import (
    auth_cookies,
    create_user,
    pack_by_slug,
    pack_by_title,
    pack_id_by_slug,
    pack_id_by_title,
)

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


@pytest.mark.workflow("WF-07")
@pytest.mark.workflow("WF-08")
@pytest.mark.anyio
async def test_completion_reflects_then_reset_clears_current_user_progress(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _record_other_user_completion("greetings", ActivityType.MATCH, 400)
    greetings_id = await pack_id_by_slug("greetings")
    events: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        "habagou.events.emit_workflow_event",
        lambda event, **fields: events.append((event, fields)),
    )

    create_response = await client.post(
        "/api/v1/progress/completions",
        json={
            "pack_id": str(greetings_id),
            "activity": "match",
            "duration_ms": 1200,
        },
    )

    assert create_response.status_code == 201
    assert create_response.json()["progress"]["match"] == {
        "completed": True,
        "completion_count": 1,
        "best_duration_ms": 1200,
    }
    assert events[0][0] == "activity_completed"
    assert events[0][1]["workflow"] == "WF-04"
    assert events[0][1]["activity"] == "match"
    assert events[0][1]["duration_ms"] == 1200

    progress_response = await client.get(f"/api/v1/progress/packs/{greetings_id}")

    assert progress_response.status_code == 200
    assert progress_response.json() == {
        "progress": {
            "trace": {
                "completed": False,
                "completion_count": 0,
                "best_duration_ms": None,
            },
            "match": {
                "completed": True,
                "completion_count": 1,
                "best_duration_ms": 1200,
            },
            "sentence": {
                "completed": False,
                "completion_count": 0,
                "best_duration_ms": None,
            },
        },
    }
    assert events[1][0] == "progress_viewed"
    assert events[1][1]["workflow"] == "WF-07"
    assert events[1][1]["pack_id"] == str(greetings_id)

    reset_response = await client.delete(f"/api/v1/progress/packs/{greetings_id}")

    assert reset_response.status_code == 200
    assert reset_response.json() == {
        "deleted_count": 1,
        "progress": {
            "trace": {
                "completed": False,
                "completion_count": 0,
                "best_duration_ms": None,
            },
            "match": {
                "completed": False,
                "completion_count": 0,
                "best_duration_ms": None,
            },
            "sentence": {
                "completed": False,
                "completion_count": 0,
                "best_duration_ms": None,
            },
        },
    }
    assert events[2][0] == "progress_reset"
    assert events[2][1]["workflow"] == "WF-08"
    assert events[2][1]["deleted_count"] == 1
    assert await _completion_count() == 1


@pytest.mark.workflow("WF-07")
@pytest.mark.anyio
async def test_completion_rejects_invalid_activity(client: AsyncClient) -> None:
    greetings_id = await pack_id_by_slug("greetings")
    response = await client.post(
        "/api/v1/progress/completions",
        json={
            "pack_id": str(greetings_id),
            "activity": "quiz",
            "duration_ms": 1200,
        },
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("activity", "workflow"),
    [
        pytest.param("trace", "WF-03", marks=pytest.mark.workflow("WF-03")),
        pytest.param("match", "WF-04", marks=pytest.mark.workflow("WF-04")),
        pytest.param("sentence", "WF-05", marks=pytest.mark.workflow("WF-05")),
    ],
)
@pytest.mark.anyio
async def test_completion_emits_activity_workflow_events(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    activity: str,
    workflow: str,
) -> None:
    greetings_id = await pack_id_by_slug("greetings")
    events: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        "habagou.events.emit_workflow_event",
        lambda event, **fields: events.append((event, fields)),
    )

    response = await client.post(
        "/api/v1/progress/completions",
        json={
            "pack_id": str(greetings_id),
            "activity": activity,
            "duration_ms": 1000,
        },
    )

    assert response.status_code == 201
    assert events[0][0] == "activity_completed"
    assert events[0][1]["workflow"] == workflow
    assert events[0][1]["activity"] == activity


@pytest.mark.workflow("WF-11")
@pytest.mark.anyio
async def test_progress_summary_returns_zero_state_for_fresh_user(
    current_user: User,
    client: AsyncClient,
) -> None:
    await _clear_user_progress(current_user.id)

    response = await client.get("/api/v1/progress/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["current_streak"] == 0
    assert body["best_streak"] == 0
    assert body["daily_goal"] == {"completed": 0, "target": 3}
    assert body["next_milestone"] == {
        "target_days": 7,
        "days_remaining": 7,
        "progress_pct": 0,
    }
    assert len(body["activity"]) == 45
    assert all(day["count"] == 0 and day["level"] == 0 for day in body["activity"])
    assert body["characters_traced"] == 0
    assert body["packs_completed"] == 0
    assert body["packs_total"] == await _enabled_pack_count(current_user.id)


@pytest.mark.workflow("WF-11")
@pytest.mark.anyio
async def test_progress_summary_current_streak_anchors_at_yesterday(
    current_user: User,
    client: AsyncClient,
) -> None:
    await _clear_user_progress(current_user.id)
    now = datetime.now(UTC)
    today = now.date()
    await _record_user_completions(
        current_user.id,
        [
            now - timedelta(days=2),
            now - timedelta(days=2, minutes=1),
            now - timedelta(days=2, minutes=2),
            now - timedelta(days=1),
            now - timedelta(days=1, minutes=1),
            now - timedelta(days=1, minutes=2),
            now,
        ],
    )

    response = await client.get("/api/v1/progress/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["current_streak"] == 2
    assert body["best_streak"] == 2
    assert body["daily_goal"] == {"completed": 1, "target": 3}
    assert body["activity"][-1]["date"] == today.isoformat()
    assert body["activity"][-1]["count"] == 1
    assert body["activity"][-1]["level"] == 1


@pytest.mark.workflow("WF-11")
@pytest.mark.anyio
async def test_progress_summary_best_streak_can_exceed_current_streak(
    current_user: User,
    client: AsyncClient,
) -> None:
    await _clear_user_progress(current_user.id)
    now = datetime.now(UTC)
    await _record_user_completions(
        current_user.id,
        [
            now - timedelta(days=8),
            now - timedelta(days=8, minutes=1),
            now - timedelta(days=8, minutes=2),
            now - timedelta(days=7),
            now - timedelta(days=7, minutes=1),
            now - timedelta(days=7, minutes=2),
            now - timedelta(days=1),
            now - timedelta(days=1, minutes=1),
            now - timedelta(days=1, minutes=2),
        ],
    )

    response = await client.get("/api/v1/progress/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["current_streak"] == 1
    assert body["best_streak"] == 2


@pytest.mark.workflow("WF-11")
@pytest.mark.anyio
async def test_progress_summary_timezone_offset_shifts_today_bucket(
    current_user: User,
    client: AsyncClient,
) -> None:
    await _clear_user_progress(current_user.id)
    await _record_user_completions(
        current_user.id, [datetime(2026, 7, 5, 1, 30, tzinfo=UTC)]
    )

    response = await client.get("/api/v1/progress/summary?tz_offset_minutes=300")

    assert response.status_code == 200
    body = response.json()
    bucket = next(day for day in body["activity"] if day["date"] == "2026-07-04")
    assert bucket["count"] == 1
    assert bucket["level"] == 1


@pytest.mark.workflow("WF-11")
@pytest.mark.anyio
async def test_progress_summary_scopes_to_current_user(client: AsyncClient) -> None:
    await _record_other_user_completion("greetings", ActivityType.TRACE, 400)

    response = await client.get("/api/v1/progress/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["daily_goal"]["completed"] == 0
    assert body["current_streak"] == 0


@pytest.mark.workflow("WF-11")
@pytest.mark.anyio
async def test_progress_summary_emits_workflow_event(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        "habagou.events.emit_workflow_event",
        lambda event, **fields: events.append((event, fields)),
    )

    response = await client.get("/api/v1/progress/summary")

    assert response.status_code == 200
    assert events[0][0] == "progress_summary_viewed"
    assert events[0][1]["workflow"] == "WF-11"
    assert "user_id" in events[0][1]
    assert "current_streak" in events[0][1]


@pytest.mark.workflow("WF-07")
@pytest.mark.workflow("WF-08")
@pytest.mark.anyio
async def test_progress_rejects_foreign_owned_pack(client: AsyncClient) -> None:
    # Recording or resetting progress on another user's private pack must 404:
    # the pack is invisible to the current user.
    async with db.async_session() as session:
        other = await create_user(session, username="other-owner", email=None)
        await session.commit()
        other_id = other.id
    foreign_id = await _create_owned_pack("foreign-progress", owner_id=other_id)

    create = await client.post(
        "/api/v1/progress/completions",
        json={"pack_id": str(foreign_id), "activity": "trace", "duration_ms": 100},
    )
    assert create.status_code == 404

    view = await client.get(f"/api/v1/progress/packs/{foreign_id}")
    assert view.status_code == 404

    reset = await client.delete(f"/api/v1/progress/packs/{foreign_id}")
    assert reset.status_code == 404


@pytest.mark.workflow("WF-07")
@pytest.mark.workflow("WF-08")
@pytest.mark.anyio
async def test_progress_404s_on_unknown_pack(client: AsyncClient) -> None:
    # A valid-but-unknown pack id 404s identically to a foreign-owned one on
    # every pack-progress endpoint (record, view, reset): no existence leak.
    unknown_id = uuid.uuid4()

    create = await client.post(
        "/api/v1/progress/completions",
        json={"pack_id": str(unknown_id), "activity": "trace", "duration_ms": 100},
    )
    assert create.status_code == 404

    view = await client.get(f"/api/v1/progress/packs/{unknown_id}")
    assert view.status_code == 404

    reset = await client.delete(f"/api/v1/progress/packs/{unknown_id}")
    assert reset.status_code == 404


@pytest.mark.workflow("WF-07")
@pytest.mark.workflow("WF-08")
@pytest.mark.anyio
async def test_progress_422s_on_malformed_id(client: AsyncClient) -> None:
    # A non-UUID pack id is rejected by validation (path param or request body)
    # before any visibility check runs.
    create = await client.post(
        "/api/v1/progress/completions",
        json={"pack_id": "not-a-uuid", "activity": "trace", "duration_ms": 100},
    )
    assert create.status_code == 422

    view = await client.get("/api/v1/progress/packs/not-a-uuid")
    assert view.status_code == 422

    reset = await client.delete("/api/v1/progress/packs/not-a-uuid")
    assert reset.status_code == 422


@pytest.mark.workflow("WF-07")
@pytest.mark.workflow("WF-08")
@pytest.mark.anyio
async def test_progress_records_on_own_owned_pack(
    client: AsyncClient,
    current_user: User,
) -> None:
    own_id = await _create_owned_pack("own-progress", owner_id=current_user.id)

    create = await client.post(
        "/api/v1/progress/completions",
        json={"pack_id": str(own_id), "activity": "trace", "duration_ms": 100},
    )
    assert create.status_code == 201
    assert create.json()["progress"]["trace"]["completed"] is True

    reset = await client.delete(f"/api/v1/progress/packs/{own_id}")
    assert reset.status_code == 200
    assert reset.json()["deleted_count"] == 1


@pytest.mark.workflow("WF-11")
@pytest.mark.anyio
async def test_progress_stats_ignore_owned_packs(
    current_user: User,
    client: AsyncClient,
) -> None:
    # packs_total counts only global Path-curriculum packs; neither the caller's
    # own private packs nor another user's owned packs affect it.
    await _clear_user_progress(current_user.id)
    async with db.async_session() as session:
        other = await create_user(session, username="other-owner", email=None)
        await session.commit()
        other_id = other.id
    global_total = await _enabled_pack_count(current_user.id)
    await _create_owned_pack("mine-stats", owner_id=current_user.id)
    await _create_owned_pack("foreign-stats", owner_id=other_id)

    response = await client.get("/api/v1/progress/summary")

    assert response.status_code == 200
    assert response.json()["packs_total"] == global_total


@pytest.mark.anyio
async def test_progress_requires_authentication() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/progress/summary")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


@pytest.mark.workflow("WF-11")
@pytest.mark.anyio
async def test_characters_traced_unions_path_and_whole_pack_trace(
    current_user: User,
    client: AsyncClient,
) -> None:
    await _clear_user_progress(current_user.id)

    path_body = await _get_path(client)
    trace_item = next(
        item for item in path_body["items"] if item["activity"] == "trace"
    )
    path_traced_hanzi = {
        char["hanzi"] for char in trace_item["content"]["trace"]["chars"]
    }
    pack_title = trace_item["pack"]["title"]

    complete_response = await _complete_path_item(client, trace_item["id"])
    assert complete_response.status_code == 201

    partial = await client.get("/api/v1/progress/summary")
    assert partial.status_code == 200
    assert partial.json()["characters_traced"] == len(path_traced_hanzi)

    pack_hanzi = await _pack_hanzi(pack_title)
    assert path_traced_hanzi <= pack_hanzi

    # Completing the whole-pack Trace activity brings in every pack character,
    # unioned with (never summed against) the chars already traced via the
    # path — otherwise this would overcount past len(pack_hanzi).
    whole_pack_response = await client.post(
        "/api/v1/progress/completions",
        json={
            "pack_id": str(await pack_id_by_title(pack_title)),
            "activity": "trace",
            "duration_ms": 900,
        },
    )
    assert whole_pack_response.status_code == 201

    summary = await client.get("/api/v1/progress/summary")
    assert summary.status_code == 200
    assert summary.json()["characters_traced"] == len(pack_hanzi)


@pytest.mark.workflow("WF-11")
@pytest.mark.anyio
async def test_packs_completed_flips_only_when_all_three_activities_done(
    current_user: User,
    client: AsyncClient,
) -> None:
    await _clear_user_progress(current_user.id)
    greetings_id = await pack_id_by_slug("greetings")

    for activity in ("trace", "match"):
        response = await client.post(
            "/api/v1/progress/completions",
            json={
                "pack_id": str(greetings_id),
                "activity": activity,
                "duration_ms": 500,
            },
        )
        assert response.status_code == 201

    partial = await client.get("/api/v1/progress/summary")
    assert partial.status_code == 200
    assert partial.json()["packs_completed"] == 0

    sentence_response = await client.post(
        "/api/v1/progress/completions",
        json={"pack_id": str(greetings_id), "activity": "sentence", "duration_ms": 500},
    )
    assert sentence_response.status_code == 201

    complete = await client.get("/api/v1/progress/summary")
    assert complete.status_code == 200
    assert complete.json()["packs_completed"] == 1


@pytest.mark.workflow("WF-11")
@pytest.mark.anyio
async def test_path_completions_alone_leave_packs_completed_at_zero(
    current_user: User,
    client: AsyncClient,
) -> None:
    await _clear_user_progress(current_user.id)

    path_body = await _get_path(client, limit=50)
    for item in path_body["items"][:5]:
        response = await _complete_path_item(client, item["id"])
        assert response.status_code == 201

    summary = await client.get("/api/v1/progress/summary")
    assert summary.status_code == 200
    assert summary.json()["packs_completed"] == 0


async def _get_path(client: AsyncClient, *, limit: int = 20):
    response = await client.get("/api/v1/path", params={"limit": limit})
    assert response.status_code == 200, response.text
    return response.json()


async def _complete_path_item(
    client: AsyncClient, item_id: str, *, duration_ms: int = 4200
):
    return await client.post(
        f"/api/v1/path/items/{item_id}/complete",
        json={"duration_ms": duration_ms},
    )


async def _pack_hanzi(title: str) -> set[str]:
    async with db.async_session() as session:
        pack = await pack_by_title(session, title)
        assert pack is not None
        return {link.character.hanzi for link in pack.characters}


async def _enabled_pack_count(user_id: uuid.UUID) -> int:
    async with db.async_session() as session:
        return len(
            await PackRepository(session).list_enabled_with_content(user_id=user_id)
        )


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


async def _record_other_user_completion(
    slug: str, activity: ActivityType, duration_ms: int
) -> None:
    async with db.async_session() as session:
        pack = await pack_by_slug(session, slug)
        assert pack is not None
        user = User(
            id=uuid.UUID("22222222-2222-4222-8222-222222222222"),
            username="other",
            display_name="Other",
            is_guest=False,
        )
        session.add(user)
        session.add(
            ActivityCompletion(
                user_id=user.id,
                pack_id=pack.id,
                activity=activity,
                duration_ms=duration_ms,
            )
        )
        await session.commit()


async def _record_user_completions(
    user_id: uuid.UUID, completed_at_values: list[datetime]
) -> None:
    async with db.async_session() as session:
        pack = await pack_by_slug(session, "greetings")
        assert pack is not None
        session.add_all(
            [
                ActivityCompletion(
                    user_id=user_id,
                    pack_id=pack.id,
                    activity=ActivityType.TRACE,
                    duration_ms=1000,
                    completed_at=completed_at,
                )
                for completed_at in completed_at_values
            ]
        )
        await session.commit()


async def _clear_user_progress(user_id: uuid.UUID) -> None:
    async with db.async_session() as session:
        for slug in ("greetings", "numbers", "family", "food-drink"):
            pack = await pack_by_slug(session, slug)
            assert pack is not None
            result = await session.execute(
                delete(ActivityCompletion).where(
                    ActivityCompletion.user_id == user_id,
                    ActivityCompletion.pack_id == pack.id,
                )
            )
            assert getattr(result, "rowcount", 0) >= 0
        await session.commit()


async def _completion_count() -> int:
    async with db.async_session() as session:
        return await session.scalar(select(func.count(ActivityCompletion.id))) or 0
