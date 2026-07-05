from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from habagou import db
from habagou.app import create_app
from habagou.models import GUEST_USER_ID, ActivityCompletion, ActivityType, User
from habagou.repositories import PackRepository

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.workflow("WF-07")
@pytest.mark.workflow("WF-08")
@pytest.mark.anyio
async def test_completion_reflects_then_reset_clears_current_user_progress(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _record_other_user_completion("greetings", ActivityType.MATCH, 400)
    events: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        "habagou.events.emit_workflow_event",
        lambda event, **fields: events.append((event, fields)),
    )

    create_response = await client.post(
        "/api/v1/progress/completions",
        json={
            "pack_slug": "greetings",
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

    progress_response = await client.get("/api/v1/progress/packs/greetings")

    assert progress_response.status_code == 200
    assert progress_response.json() == {
        "pack_slug": "greetings",
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
    assert events[1][1]["pack_slug"] == "greetings"

    reset_response = await client.delete("/api/v1/progress/packs/greetings")

    assert reset_response.status_code == 200
    assert reset_response.json() == {
        "pack_slug": "greetings",
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
    response = await client.post(
        "/api/v1/progress/completions",
        json={
            "pack_slug": "greetings",
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
    events: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        "habagou.events.emit_workflow_event",
        lambda event, **fields: events.append((event, fields)),
    )

    response = await client.post(
        "/api/v1/progress/completions",
        json={
            "pack_slug": "greetings",
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
    client: AsyncClient,
) -> None:
    await _clear_guest_progress()

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


@pytest.mark.workflow("WF-11")
@pytest.mark.anyio
async def test_progress_summary_current_streak_anchors_at_yesterday(
    client: AsyncClient,
) -> None:
    await _clear_guest_progress()
    now = datetime.now(UTC)
    today = now.date()
    await _record_guest_completions(
        [
            now - timedelta(days=2),
            now - timedelta(days=2, minutes=1),
            now - timedelta(days=2, minutes=2),
            now - timedelta(days=1),
            now - timedelta(days=1, minutes=1),
            now - timedelta(days=1, minutes=2),
            now,
        ]
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
    client: AsyncClient,
) -> None:
    await _clear_guest_progress()
    now = datetime.now(UTC)
    await _record_guest_completions(
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
        ]
    )

    response = await client.get("/api/v1/progress/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["current_streak"] == 1
    assert body["best_streak"] == 2


@pytest.mark.workflow("WF-11")
@pytest.mark.anyio
async def test_progress_summary_timezone_offset_shifts_today_bucket(
    client: AsyncClient,
) -> None:
    await _clear_guest_progress()
    await _record_guest_completions([datetime(2026, 7, 5, 1, 30, tzinfo=UTC)])

    response = await client.get("/api/v1/progress/summary?tz_offset_minutes=300")

    assert response.status_code == 200
    body = response.json()
    bucket = next(day for day in body["activity"] if day["date"] == "2026-07-04")
    assert bucket["count"] == 1
    assert bucket["level"] == 1


@pytest.mark.workflow("WF-11")
@pytest.mark.anyio
async def test_progress_summary_scopes_to_current_user(client: AsyncClient) -> None:
    await _clear_guest_progress()
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


async def _record_other_user_completion(
    slug: str, activity: ActivityType, duration_ms: int
) -> None:
    async with db.async_session() as session:
        pack = await PackRepository(session).get_by_slug(slug)
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


async def _record_guest_completions(completed_at_values: list[datetime]) -> None:
    async with db.async_session() as session:
        user = await session.get(User, GUEST_USER_ID)
        pack = await PackRepository(session).get_by_slug("greetings")
        assert user is not None
        assert pack is not None
        session.add_all(
            [
                ActivityCompletion(
                    user_id=user.id,
                    pack_id=pack.id,
                    activity=ActivityType.TRACE,
                    duration_ms=1000,
                    completed_at=completed_at,
                )
                for completed_at in completed_at_values
            ]
        )
        await session.commit()


async def _clear_guest_progress() -> None:
    async with db.async_session() as session:
        user = await session.get(User, GUEST_USER_ID)
        assert user is not None
        for slug in ("greetings", "numbers", "family", "food-drink"):
            pack = await PackRepository(session).get_by_slug(slug)
            assert pack is not None
            result = await session.execute(
                delete(ActivityCompletion).where(
                    ActivityCompletion.user_id == user.id,
                    ActivityCompletion.pack_id == pack.id,
                )
            )
            assert getattr(result, "rowcount", 0) >= 0
        await session.commit()


async def _completion_count() -> int:
    async with db.async_session() as session:
        return await session.scalar(select(func.count(ActivityCompletion.id))) or 0
