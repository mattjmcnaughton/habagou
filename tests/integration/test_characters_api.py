from __future__ import annotations

import statistics
import time
from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient

from habagou.app import create_app
from habagou.routers.v1.characters import CACHE_CONTROL_IMMUTABLE

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.workflow("WF-06")
@pytest.mark.anyio
async def test_get_character_strokes_returns_hanzi_writer_json(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/characters/你/strokes")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == CACHE_CONTROL_IMMUTABLE
    body = response.json()
    assert isinstance(body["strokes"], list)
    assert isinstance(body["medians"], list)
    assert body["strokes"]
    assert body["medians"]


@pytest.mark.workflow("WF-06")
@pytest.mark.anyio
async def test_get_character_strokes_rejects_multi_grapheme(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/characters/你好/strokes")

    assert response.status_code == 422


@pytest.mark.workflow("WF-06")
@pytest.mark.anyio
async def test_get_character_strokes_404s_for_unknown_and_emits_event(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        "habagou.routers.v1.characters.emit_workflow_event",
        lambda event, **fields: events.append((event, fields)),
    )

    response = await client.get("/api/v1/characters/☂/strokes")

    assert response.status_code == 404
    assert events == [
        (
            "strokes_missing",
            {
                "workflow": "WF-06",
                "outcome": "error",
                "duration_ms": events[0][1]["duration_ms"],
                "hanzi": "☂",
            },
        )
    ]


@pytest.mark.workflow("WF-06")
@pytest.mark.anyio
async def test_get_character_strokes_local_p95_under_50ms(client: AsyncClient) -> None:
    warmup = await client.get("/api/v1/characters/你/strokes")
    assert warmup.status_code == 200

    timings: list[float] = []
    for _ in range(20):
        started_at = time.perf_counter()
        response = await client.get("/api/v1/characters/你/strokes")
        timings.append((time.perf_counter() - started_at) * 1000)
        assert response.status_code == 200

    p95 = statistics.quantiles(timings, n=20)[18]
    assert p95 < 50
