"""Integration tests for the conversational practice endpoints (WF-16).

The real app is exercised end-to-end through ``ASGITransport``: the real
practice agent runs with only the *model* stubbed, using pydantic-ai's
``FunctionModel`` via ``Agent.override(model=...)``. As with the generation
tests, ``Agent.override`` takes precedence over the ``model=`` argument the
service passes to ``agent.run`` — but the service still reaches
``_build_model()``, so the configured tests set ``openrouter_api_key`` (the
real OpenRouter model is *built*, no network I/O, but never *called*).

Practice touches no database of its own; Postgres is only involved through
the auth dependency resolving the current user.
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
from habagou.services.practice_chat import get_practice_agent
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


def _segment(hanzi: str) -> dict[str, str]:
    return {"hanzi": hanzi, "pinyin": "x", "english": "x"}


def _turn(*hanzi: str, english_aside: str | None = None) -> dict[str, object]:
    turn: dict[str, object] = {"segments": [_segment(char) for char in hanzi]}
    if english_aside is not None:
        turn["english_aside"] = english_aside
    return turn


class _Responder:
    """A ``FunctionModel`` callback emitting ``turns`` in order, one per call."""

    __name__ = "responder"

    def __init__(self, turns: list[dict[str, object]]) -> None:
        self._turns = turns
        self.call_count = 0
        self.messages_per_call: list[list[ModelMessage]] = []

    def __call__(
        self, messages: Sequence[ModelMessage], info: AgentInfo
    ) -> ModelResponse:
        self.messages_per_call.append(list(messages))
        turn = self._turns[self.call_count]
        self.call_count += 1
        return ModelResponse(
            parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=turn)]
        )


def _prompt_texts(messages: Sequence[ModelMessage]) -> list[str]:
    return [
        part.content
        for message in messages
        for part in getattr(message, "parts", [])
        if isinstance(part, UserPromptPart) and isinstance(part.content, str)
    ]


@pytest.mark.anyio
@pytest.mark.workflow("WF-16")
async def test_turn_returns_segments_and_history(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")
    respond = _Responder([_turn("你好", "你想吃什么")])

    with get_practice_agent().override(model=FunctionModel(respond)):
        response = await client.post(
            "/api/v1/practice/turn", json={"message": "ordering food"}
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert [segment["hanzi"] for segment in body["turn"]["segments"]] == [
        "你好",
        "你想吃什么",
    ]
    # Every segment carries all three renderings (the tap-reveal contract).
    for segment in body["turn"]["segments"]:
        assert segment["pinyin"]
        assert segment["english"]
    assert body["turn"]["english_aside"] is None
    # The updated conversation history is returned for the client to hold.
    assert isinstance(body["history"], list)
    assert body["history"]


@pytest.mark.anyio
@pytest.mark.workflow("WF-16")
async def test_follow_up_turn_replays_prior_history(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")
    respond = _Responder([_turn("你好"), _turn("我很好")])

    with get_practice_agent().override(model=FunctionModel(respond)):
        first = await client.post(
            "/api/v1/practice/turn", json={"message": "ordering food"}
        )
        assert first.status_code == 200, first.text
        history = first.json()["history"]

        second = await client.post(
            "/api/v1/practice/turn",
            json={"message": "你好吗", "history": history},
        )

    assert second.status_code == 200, second.text
    assert [segment["hanzi"] for segment in second.json()["turn"]["segments"]] == [
        "我很好"
    ]
    # The follow-up turn's model call actually saw the first turn's prompt,
    # proving the opaque history round-tripped through the endpoint.
    prompts = _prompt_texts(respond.messages_per_call[1])
    assert any("ordering food" in text for text in prompts)
    assert any("你好吗" in text for text in prompts)


@pytest.mark.anyio
@pytest.mark.workflow("WF-16")
async def test_turn_surfaces_english_aside(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")
    respond = _Responder(
        [_turn("我们继续吧", english_aside="它 means 'it' — used for things.")]
    )

    with get_practice_agent().override(model=FunctionModel(respond)):
        response = await client.post(
            "/api/v1/practice/turn", json={"message": "what does 它 mean?"}
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["turn"]["english_aside"] == "它 means 'it' — used for things."
    # The Chinese conversation continues in the same turn.
    assert body["turn"]["segments"]


@pytest.mark.anyio
@pytest.mark.workflow("WF-16")
async def test_turn_requires_authentication() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/practice/turn", json={"message": "ordering food"}
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


@pytest.mark.anyio
@pytest.mark.workflow("WF-16")
async def test_turn_503_when_practice_unconfigured(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No OpenRouter key: _build_model raises PracticeNotConfiguredError, which
    # the endpoint maps to 503 / service_unavailable.
    monkeypatch.setattr(settings, "openrouter_api_key", "")

    response = await client.post(
        "/api/v1/practice/turn", json={"message": "ordering food"}
    )

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "service_unavailable"
    assert "not configured" in body["error"]["message"]


@pytest.mark.anyio
@pytest.mark.workflow("WF-16")
async def test_turn_422_on_malformed_history(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The client-held history is opaque JSON; a corrupted or hand-crafted
    # payload must surface as the caller's error, never a 500.
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")

    response = await client.post(
        "/api/v1/practice/turn",
        json={"message": "你好", "history": [{"not": "a valid message"}]},
    )

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert "history" in body["error"]["message"]


@pytest.mark.anyio
@pytest.mark.workflow("WF-16")
async def test_turn_502_on_provider_connection_failure(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")

    def explode(messages: Sequence[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise ModelAPIError(
            model_name="deepseek/deepseek-v4-flash", message="conn refused"
        )

    with get_practice_agent().override(model=FunctionModel(explode)):
        response = await client.post(
            "/api/v1/practice/turn", json={"message": "ordering food"}
        )

    assert response.status_code == 502, response.text
    assert response.json()["error"]["code"] == "bad_gateway"


@pytest.mark.anyio
@pytest.mark.workflow("WF-16")
async def test_turn_rate_limit_is_per_user(
    current_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The limiter is built in create_app() from the setting, so the cap must be
    # in place BEFORE the app is constructed (not via the shared client fixture).
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")
    monkeypatch.setattr(settings, "practice_rate_limit_per_hour", 2)

    async with db.async_session() as session:
        other = await create_user(session, username="practice-rate-other", email=None)
        await session.commit()
        other_id = other.id

    respond = _Responder([_turn("你") for _ in range(4)])

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        client.cookies.update(auth_cookies(current_user.id))
        with get_practice_agent().override(model=FunctionModel(respond)):
            first = await client.post("/api/v1/practice/turn", json={"message": "你"})
            second = await client.post("/api/v1/practice/turn", json={"message": "你"})
            third = await client.post("/api/v1/practice/turn", json={"message": "你"})

            assert first.status_code == 200, first.text
            assert second.status_code == 200, second.text
            # The third attempt inside the window is over the cap of 2.
            assert third.status_code == 429, third.text
            assert third.json()["error"]["code"] == "rate_limited"

            # A different user has an independent window and still gets through.
            client.cookies.update(auth_cookies(other_id))
            other_response = await client.post(
                "/api/v1/practice/turn", json={"message": "你"}
            )
            assert other_response.status_code == 200, other_response.text


@pytest.mark.anyio
@pytest.mark.workflow("WF-16")
async def test_practice_limiter_is_independent_of_generation_limiter(
    current_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Exhausting the practice window must not consume generation quota (and
    # vice versa): the two features cap billed spend separately.
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    monkeypatch.setattr(settings, "practice_rate_limit_per_hour", 1)
    monkeypatch.setattr(settings, "generation_rate_limit_per_hour", 1)

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        client.cookies.update(auth_cookies(current_user.id))
        # Unconfigured attempts still consume quota (count-on-attempt).
        burned = await client.post("/api/v1/practice/turn", json={"message": "你"})
        assert burned.status_code == 503, burned.text
        over = await client.post("/api/v1/practice/turn", json={"message": "你"})
        assert over.status_code == 429, over.text

        # The generation window is untouched: its first attempt still reaches
        # the (unconfigured) 503, not a 429.
        draft = await client.post("/api/v1/generation/draft", json={"topic": "t"})
        assert draft.status_code == 503, draft.text


# --- Status probe (entry-point gating) ------------------------------------------


@pytest.mark.anyio
async def test_status_reports_disabled_when_practice_unconfigured(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Pinned to "" so the result is independent of the test env.
    monkeypatch.setattr(settings, "openrouter_api_key", "")

    response = await client.get("/api/v1/practice/status")

    assert response.status_code == 200, response.text
    assert response.json() == {"enabled": False, "models": None, "default_model": None}


@pytest.mark.anyio
async def test_status_reports_enabled_when_practice_configured(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")

    response = await client.get("/api/v1/practice/status")

    assert response.status_code == 200, response.text
    assert response.json() == {"enabled": True, "models": None, "default_model": None}


@pytest.mark.anyio
async def test_status_requires_authentication() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/practice/status")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


# --- Admin model selection ------------------------------------------------------


@pytest.fixture
async def admin_client() -> AsyncGenerator[AsyncClient]:
    async with db.async_session() as session:
        admin = await create_user(
            session, username="practice-admin", email="matt@mattjmcnaughton.com"
        )
        await session.commit()
        admin_id = admin.id
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        client.cookies.update(auth_cookies(admin_id))
        yield client


@pytest.mark.anyio
async def test_status_lists_models_for_admin(
    admin_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")

    response = await admin_client.get("/api/v1/practice/status")

    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is True
    assert body["default_model"] == settings.practice_model
    assert [option["id"] for option in body["models"]] == list(
        settings.practice_model_ids
    )


@pytest.mark.anyio
async def test_status_hides_models_from_non_admin(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")

    response = await client.get("/api/v1/practice/status")

    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is True
    assert body["models"] is None
    assert body["default_model"] is None


@pytest.mark.anyio
@pytest.mark.workflow("WF-16")
async def test_turn_accepts_allowlisted_model_from_admin(
    admin_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")
    respond = _Responder([_turn("你好")])

    with get_practice_agent().override(model=FunctionModel(respond)):
        response = await admin_client.post(
            "/api/v1/practice/turn",
            json={"message": "ordering food", "model": "minimax/minimax-m3"},
        )

    assert response.status_code == 200, response.text
    assert respond.call_count == 1


@pytest.mark.anyio
async def test_turn_rejects_model_from_non_admin(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")

    response = await client.post(
        "/api/v1/practice/turn",
        json={"message": "ordering food", "model": "minimax/minimax-m3"},
    )

    assert response.status_code == 403
    assert "admin" in response.json()["error"]["message"]


@pytest.mark.anyio
async def test_turn_rejects_model_outside_allowlist(
    admin_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")

    response = await admin_client.post(
        "/api/v1/practice/turn",
        json={"message": "ordering food", "model": "someone/not-a-real-model"},
    )

    assert response.status_code == 422
    assert "minimax/minimax-m3" in response.json()["error"]["message"]
