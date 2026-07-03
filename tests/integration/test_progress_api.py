from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from habagou import db
from habagou.app import create_app
from habagou.models import ActivityCompletion, ActivityType, User
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
        "habagou.routers.v1.progress.emit_workflow_event",
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
    assert events[1][0] == "progress_reset"
    assert events[1][1]["workflow"] == "WF-08"
    assert events[1][1]["deleted_count"] == 1
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
        "habagou.routers.v1.progress.emit_workflow_event",
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


async def _completion_count() -> int:
    async with db.async_session() as session:
        return await session.scalar(select(func.count(ActivityCompletion.id))) or 0
