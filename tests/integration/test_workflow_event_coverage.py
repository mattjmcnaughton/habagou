from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import update

from habagou import db
from habagou.app import create_app
from habagou.auth import AuthIdentity
from habagou.config import settings
from habagou.models import ReviewState
from habagou.repositories import UserRepository
from scripts.seed import SeedResult, emit_bootstrap_completed

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

_WORKFLOW_ISSUER = "https://issuer.example.test"
_WORKFLOW_SUBJECT = "workflow-subject"


EXPECTED_EVENTS: dict[str, tuple[set[str], set[str], str]] = {
    "WF-01": (
        {"bootstrap_completed"},
        {"chars_imported", "packs_seeded", "migrations_applied"},
        "ok",
    ),
    "WF-02": ({"pack_list_served", "pack_served"}, {"pack_count"}, "ok"),
    "WF-03": ({"activity_completed"}, {"activity", "pack_slug", "user_id"}, "ok"),
    "WF-04": ({"activity_completed"}, {"activity", "pack_slug", "user_id"}, "ok"),
    "WF-05": ({"activity_completed"}, {"activity", "pack_slug", "user_id"}, "ok"),
    "WF-06": ({"strokes_served", "strokes_missing"}, {"hanzi", "found"}, "ok"),
    "WF-07": ({"progress_viewed"}, {"pack_slug", "user_id"}, "ok"),
    "WF-08": ({"progress_reset"}, {"pack_slug", "deleted_count", "user_id"}, "ok"),
    "WF-09": ({"admin_action"}, {"action", "pack_slug", "authorized"}, "ok"),
    "WF-10": ({"deploy_ready"}, {"database"}, "ok"),
    "WF-11": ({"progress_summary_viewed"}, {"user_id", "current_streak"}, "ok"),
    "WF-12": (
        {"path_viewed"},
        {"user_id", "item_count", "due_new", "due_review"},
        "ok",
    ),
    "WF-13": (
        {"path_item_completed"},
        {"activity", "pack_slug", "kind", "user_id"},
        "ok",
    ),
    "WF-14": (
        {"path_item_completed"},
        {"activity", "pack_slug", "kind", "user_id"},
        "ok",
    ),
    "WF-AUTH-SIGN-IN": ({"auth_signed_in"}, {"user_id", "provider"}, "ok"),
    "WF-AUTH-SIGN-OUT": ({"auth_signed_out"}, {"user_id", "provider"}, "ok"),
    "WF-AUTH-GATE": ({"auth_gate_rejected"}, {"path"}, "error"),
}


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.anyio
async def test_all_workflows_emit_verification_events(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emitted: list[tuple[str, dict[str, Any]]] = []

    class StubLogger:
        def info(self, event: str, **fields: Any) -> None:
            emitted.append((event, fields))

    monkeypatch.setattr(
        "habagou.events.structlog.get_logger", lambda _name: StubLogger()
    )
    monkeypatch.setattr(settings, "admin_token", "secret")
    monkeypatch.setattr(
        "habagou.routers.auth.oauth.create_client",
        lambda _provider: StubOAuthClient(),
    )
    monkeypatch.setattr(
        "habagou.routers.auth.fetch_identity",
        lambda *_args: AuthIdentity(
            issuer="https://issuer.example.test",
            subject="workflow-subject",
            username="workflow-user",
            display_name="Workflow User",
        ),
    )

    emit_bootstrap_completed(SeedResult(chars=20, packs=4))
    await _ok(await client.get("/auth/callback"), status_code=303)
    await _ok(await client.get("/api/v1/packs"))
    for activity in ("trace", "match", "sentence"):
        await _ok(
            await client.post(
                "/api/v1/progress/completions",
                json={
                    "pack_slug": "greetings",
                    "activity": activity,
                    "duration_ms": 1000,
                },
            ),
            status_code=201,
        )
    await _ok(await client.get("/api/v1/characters/你/strokes"))
    await _ok(await client.get("/api/v1/progress/packs/greetings"))
    await _ok(await client.get("/api/v1/progress/summary"))
    # WF-12: view the path (also materializes the queue).
    path_body = await _json(await client.get("/api/v1/path"))
    new_item = next(
        item
        for item in path_body["items"]
        if item["kind"] == "new" and item["state"] != "done"
    )
    # WF-13: complete a new path item.
    await _ok(
        await client.post(
            f"/api/v1/path/items/{new_item['id']}/complete",
            json={"duration_ms": 900},
        ),
        status_code=201,
    )
    # WF-14: backdate the completed unit and complete the resurfaced review item.
    await _backdate_path_reviews()
    review_body = await _json(await client.get("/api/v1/path?limit=50"))
    review_item = next(
        item
        for item in review_body["items"]
        if item["kind"] == "review" and item["state"] != "done"
    )
    await _ok(
        await client.post(
            f"/api/v1/path/items/{review_item['id']}/complete",
            json={"duration_ms": 900},
        ),
        status_code=201,
    )
    await _ok(await client.delete("/api/v1/progress/packs/greetings"))
    await _ok(
        await client.patch(
            "/api/v1/admin/packs/greetings",
            headers={"ADMIN_TOKEN": "secret"},
            json={"sort_order": 1},
        )
    )
    await _ok(await client.get("/readyz"))
    await _ok(await client.post("/auth/logout"), status_code=204)
    await _ok(await client.get("/api/v1/packs"), status_code=401)

    assert set(EXPECTED_EVENTS) == _workflow_ids_from_catalog()
    for workflow, (
        event_names,
        extra_fields,
        expected_outcome,
    ) in EXPECTED_EVENTS.items():
        matches = [
            (event, fields)
            for event, fields in emitted
            if fields.get("workflow") == workflow and event in event_names
        ]
        assert matches, f"{workflow} did not emit one of {sorted(event_names)}"
        event, fields = matches[0]
        assert fields["outcome"] == expected_outcome, event
        assert isinstance(fields["duration_ms"], int), event
        assert extra_fields <= fields.keys(), event


async def _ok(response, *, status_code: int = 200) -> None:
    assert response.status_code == status_code, response.text


async def _json(response, *, status_code: int = 200) -> dict[str, Any]:
    assert response.status_code == status_code, response.text
    return response.json()


async def _backdate_path_reviews() -> None:
    """Force the workflow user's practised review states past due."""
    async with db.async_session() as session:
        user = await UserRepository(session).get_by_identity(
            _WORKFLOW_ISSUER, _WORKFLOW_SUBJECT
        )
        assert user is not None
        await session.execute(
            update(ReviewState)
            .where(
                ReviewState.user_id == user.id,
                ReviewState.due_at.is_not(None),
            )
            .values(due_at=datetime.now(UTC) - timedelta(days=2))
        )
        await session.commit()


def _workflow_ids_from_catalog() -> set[str]:
    pattern = re.compile(r"^\s*-\s*id:\s*(WF-[A-Z0-9-]+)\s*$")
    ids: set[str] = set()
    for line in (
        Path("src/habagou/workflows.yml").read_text(encoding="utf-8").splitlines()
    ):
        match = pattern.match(line)
        if match:
            ids.add(match.group(1))
    return ids


class StubOAuthClient:
    async def authorize_access_token(self, _request):
        return {"access_token": "stub"}
