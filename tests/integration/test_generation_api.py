"""Integration tests for the pack-generation draft endpoint (HAB-083).

The real app is exercised end-to-end through ``ASGITransport``: the real
generation agent, its ``find_characters`` tool, and its output validator all run
against real Postgres (the seeded stroke corpus). Only the *model* is stubbed,
using pydantic-ai's ``FunctionModel`` via ``Agent.override(model=...)``.

Empirically (pydantic-ai 2.5.0), ``Agent.override(model=...)`` takes precedence
over the ``model=`` argument ``generate_pack_draft`` passes to ``agent.run``, so
the service still reaches ``_build_model()`` — which raises when generation is
unconfigured. We therefore set ``openrouter_api_key`` in the configured tests so
the real OpenRouter model is *built* (no network I/O) but never *called*, because
the override wins. ``FunctionModel`` needs no live provider and is unaffected by
the suite-wide ``ALLOW_MODEL_REQUESTS = False`` guard.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic_ai.exceptions import ModelAPIError
from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from habagou import db
from habagou.app import create_app
from habagou.config import settings
from habagou.services.pack_generation import get_generation_agent
from tests.integration.conftest import auth_cookies, create_user

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Sequence

    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models.function import AgentInfo

    from habagou.models import User


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


def _character(hanzi: str) -> dict[str, str]:
    return {"hanzi": hanzi, "pinyin": "x", "meaning": "x"}


def _draft(title: str, hanzi: list[str]) -> dict[str, object]:
    return {"title": title, "characters": [_character(char) for char in hanzi]}


class _Responder:
    """A ``FunctionModel`` callback emitting ``drafts`` in order, one per call.

    Records the messages each call received (so a refinement turn can assert it
    saw the prior turn's prompt) and its ``call_count`` (so a retry is provable).
    """

    __name__ = "responder"

    def __init__(self, drafts: list[dict[str, object]]) -> None:
        self._drafts = drafts
        self.call_count = 0
        self.messages_per_call: list[list[ModelMessage]] = []

    def __call__(
        self, messages: Sequence[ModelMessage], info: AgentInfo
    ) -> ModelResponse:
        self.messages_per_call.append(list(messages))
        draft = self._drafts[self.call_count]
        self.call_count += 1
        return ModelResponse(
            parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=draft)]
        )


def _prompt_texts(messages: Sequence[ModelMessage]) -> list[str]:
    return [
        part.content
        for message in messages
        for part in getattr(message, "parts", [])
        if isinstance(part, UserPromptPart) and isinstance(part.content, str)
    ]


@pytest.mark.anyio
async def test_draft_returns_corpus_valid_draft_and_history(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")
    respond = _Responder([_draft("Greetings", ["你", "好"])])

    with get_generation_agent().override(model=FunctionModel(respond)):
        response = await client.post(
            "/api/v1/generation/draft", json={"topic": "greetings"}
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["draft"]["title"] == "Greetings"
    assert [c["hanzi"] for c in body["draft"]["characters"]] == ["你", "好"]
    # The updated conversation history is returned for the client to persist.
    assert isinstance(body["history"], list)
    assert body["history"]


@pytest.mark.anyio
async def test_draft_retries_through_postgres_grounding(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")
    # 龘 is absent from the seeded corpus: the output validator (querying real
    # Postgres) raises ModelRetry, so the model is re-invoked into a valid draft.
    respond = _Responder(
        [
            _draft("First", ["你", "龘"]),
            _draft("Second", ["你", "好"]),
        ]
    )

    with get_generation_agent().override(model=FunctionModel(respond)):
        response = await client.post(
            "/api/v1/generation/draft", json={"topic": "greetings"}
        )

    assert response.status_code == 200, response.text
    # The retry happened (proving corpus validation against Postgres), and the
    # grounded draft won.
    assert respond.call_count == 2
    assert response.json()["draft"]["title"] == "Second"


@pytest.mark.anyio
async def test_draft_requires_authentication() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/generation/draft", json={"topic": "greetings"}
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


@pytest.mark.anyio
async def test_draft_503_when_generation_unconfigured(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No OpenRouter key: _build_model raises GenerationNotConfiguredError, which
    # the endpoint maps to 503 / service_unavailable.
    monkeypatch.setattr(settings, "openrouter_api_key", "")

    response = await client.post(
        "/api/v1/generation/draft", json={"topic": "greetings"}
    )

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "service_unavailable"
    assert "not configured" in body["error"]["message"]


@pytest.mark.anyio
async def test_draft_refinement_turn_replays_prior_history(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")
    respond = _Responder(
        [
            _draft("First", ["你"]),
            _draft("Second", ["你", "好"]),
        ]
    )

    with get_generation_agent().override(model=FunctionModel(respond)):
        first = await client.post(
            "/api/v1/generation/draft",
            json={"topic": "greetings for beginners"},
        )
        assert first.status_code == 200, first.text
        history = first.json()["history"]

        second = await client.post(
            "/api/v1/generation/draft",
            json={"topic": "make it harder", "history": history},
        )

    assert second.status_code == 200, second.text
    assert second.json()["draft"]["title"] == "Second"
    # The refinement turn's model call actually saw the first turn's prompt,
    # proving the opaque history round-tripped through the endpoint.
    prompts = _prompt_texts(respond.messages_per_call[1])
    assert any("greetings for beginners" in text for text in prompts)
    assert any("make it harder" in text for text in prompts)


@pytest.mark.anyio
async def test_draft_422_on_malformed_history(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The client-held history is opaque JSON; a corrupted or hand-crafted
    # payload must surface as the caller's error, never a 500.
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")

    response = await client.post(
        "/api/v1/generation/draft",
        json={"topic": "greetings", "history": [{"not": "a valid message"}]},
    )

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert "history" in body["error"]["message"]


@pytest.mark.anyio
async def test_draft_502_on_provider_connection_failure(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A network failure reaching the provider raises ModelAPIError (not its
    # ModelHTTPError subclass); the endpoint maps it to 502, not 500.
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")

    def explode(messages: Sequence[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise ModelAPIError(model_name="openai/gpt-5-mini", message="conn refused")

    with get_generation_agent().override(model=FunctionModel(explode)):
        response = await client.post(
            "/api/v1/generation/draft", json={"topic": "greetings"}
        )

    assert response.status_code == 502, response.text
    assert response.json()["error"]["code"] == "bad_gateway"


# --- HAB-084: save endpoint ----------------------------------------------------


def _sentence(hanzi: str) -> dict[str, str]:
    return {"hanzi": hanzi, "pinyin": "x", "translation": "x"}


def _save_body(
    title: str,
    hanzi: list[str],
    sentences: list[str] | None = None,
) -> dict[str, object]:
    draft: dict[str, object] = {
        "title": title,
        "characters": [_character(char) for char in hanzi],
    }
    if sentences is not None:
        draft["sentences"] = [_sentence(text) for text in sentences]
    return {"draft": draft}


@pytest.mark.anyio
async def test_save_persists_owned_pack_visible_to_owner(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/generation/packs",
        json=_save_body("My Saved Pack", ["你", "好", "我"], sentences=["你好"]),
    )

    assert response.status_code == 201, response.text
    detail = response.json()
    pack_id = detail["id"]
    assert detail["title"] == "My Saved Pack"
    # glyph defaults to the first character's hanzi; color is a curated pick.
    assert detail["glyph"] == "你"
    assert detail["color"] in {"#c4633f", "#3f8a86", "#5b5fa8", "#b5852e"}
    assert [c["hanzi"] for c in detail["characters"]] == ["你", "好", "我"]
    assert [s["hanzi"] for s in detail["sentences"]] == ["你好"]

    # It shows up in the owner's catalog (list_visible)...
    listed = await client.get("/api/v1/packs")
    assert listed.status_code == 200
    assert pack_id in {pack["id"] for pack in listed.json()}

    # ...and its full detail is retrievable (traceable end to end).
    fetched = await client.get(f"/api/v1/packs/{pack_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == pack_id


@pytest.mark.anyio
async def test_saved_pack_is_invisible_to_other_users(
    client: AsyncClient,
) -> None:
    created = await client.post(
        "/api/v1/generation/packs",
        json=_save_body("Private Pack", ["你", "好"]),
    )
    assert created.status_code == 201, created.text
    pack_id = created.json()["id"]

    async with db.async_session() as session:
        other = await create_user(session, username="other-gen-user", email=None)
        await session.commit()
        other_id = other.id
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as other:
        other.cookies.update(auth_cookies(other_id))

        catalog = await other.get("/api/v1/packs")
        assert catalog.status_code == 200
        assert pack_id not in {pack["id"] for pack in catalog.json()}

        # A foreign owned pack is indistinguishable from a missing one: 404.
        detail = await other.get(f"/api/v1/packs/{pack_id}")
        assert detail.status_code == 404


@pytest.mark.anyio
async def test_save_422_on_non_corpus_glyph(client: AsyncClient) -> None:
    # POST straight to save (bypassing the grounded draft endpoint) with a
    # non-corpus character: the repository (layer 3) rejects it, surfaced as 422.
    response = await client.post(
        "/api/v1/generation/packs",
        json=_save_body("Ungrounded", ["你", "龘"]),
    )

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert "龘" in body["error"]["message"]


@pytest.mark.anyio
async def test_save_requires_authentication() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/generation/packs",
            json=_save_body("Nope", ["你"]),
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


@pytest.mark.anyio
async def test_path_serves_only_global_content_after_save(
    client: AsyncClient,
) -> None:
    # The Learning Path is global-only: saving an owned pack must not inject it
    # into the path (a decided Epic-7 invariant).
    created = await client.post(
        "/api/v1/generation/packs",
        json=_save_body("Path Excluded", ["你", "好"]),
    )
    assert created.status_code == 201, created.text
    saved_title = created.json()["title"]

    path = await client.get("/api/v1/path")
    assert path.status_code == 200
    pack_titles = {item["pack"]["title"] for item in path.json()["items"]}
    assert saved_title not in pack_titles
    # The path is still populated from the seeded global packs.
    assert pack_titles <= {"Greetings", "Numbers", "Family", "Food & drink"}
