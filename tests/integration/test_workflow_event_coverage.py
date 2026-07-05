from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from httpx import ASGITransport, AsyncClient

from habagou.app import create_app
from habagou.config import settings
from scripts.seed import SeedResult, emit_bootstrap_completed

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


EXPECTED_EVENTS: dict[str, tuple[set[str], set[str]]] = {
    "WF-01": (
        {"bootstrap_completed"},
        {"chars_imported", "packs_seeded", "migrations_applied"},
    ),
    "WF-02": ({"pack_list_served", "pack_served"}, {"pack_count"}),
    "WF-03": ({"activity_completed"}, {"activity", "pack_slug", "user_id"}),
    "WF-04": ({"activity_completed"}, {"activity", "pack_slug", "user_id"}),
    "WF-05": ({"activity_completed"}, {"activity", "pack_slug", "user_id"}),
    "WF-06": ({"strokes_served", "strokes_missing"}, {"hanzi", "found"}),
    "WF-07": ({"progress_viewed"}, {"pack_slug", "user_id"}),
    "WF-08": ({"progress_reset"}, {"pack_slug", "deleted_count", "user_id"}),
    "WF-09": ({"admin_action"}, {"action", "pack_slug", "authorized"}),
    "WF-10": ({"deploy_ready"}, {"database"}),
    "WF-11": ({"progress_summary_viewed"}, {"user_id", "current_streak"}),
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

    emit_bootstrap_completed(SeedResult(chars=20, packs=4))
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
    await _ok(await client.delete("/api/v1/progress/packs/greetings"))
    await _ok(
        await client.patch(
            "/api/v1/admin/packs/greetings",
            headers={"ADMIN_TOKEN": "secret"},
            json={"sort_order": 1},
        )
    )
    await _ok(await client.get("/readyz"))

    assert set(EXPECTED_EVENTS) == _workflow_ids_from_docs()
    for workflow, (event_names, extra_fields) in EXPECTED_EVENTS.items():
        matches = [
            (event, fields)
            for event, fields in emitted
            if fields.get("workflow") == workflow and event in event_names
        ]
        assert matches, f"{workflow} did not emit one of {sorted(event_names)}"
        event, fields = matches[0]
        assert fields["outcome"] == "ok", event
        assert isinstance(fields["duration_ms"], int), event
        assert extra_fields <= fields.keys(), event


async def _ok(response, *, status_code: int = 200) -> None:
    assert response.status_code == status_code, response.text


def _workflow_ids_from_docs() -> set[str]:
    pattern = re.compile(r"^\s*-\s*id:\s*(WF-\d{2})\s*$")
    ids: set[str] = set()
    for line in Path("docs/workflows.yml").read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            ids.add(match.group(1))
    return ids
