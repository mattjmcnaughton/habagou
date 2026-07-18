"""Unit tests for the conversational practice tutor service (WF-16).

No network and no database: the model is stubbed with pydantic-ai's
``FunctionModel``/``TestModel``, mirroring ``test_pack_generation.py``. The
practice agent has no tools and no output validator, so these tests focus on
the structured ``PracticeTurn`` output, the client-held history round trip,
and the configuration gate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.openai import OpenAIChatModel

from habagou.dtos.practice import PracticeTurn
from habagou.services import practice_chat
from habagou.services.practice_chat import (
    PracticeNotConfiguredError,
    run_practice_turn,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pydantic_ai.messages import ModelMessage


def _segment(hanzi: str) -> dict[str, str]:
    return {"hanzi": hanzi, "pinyin": "x", "english": "x"}


def _turn(*hanzi: str, english_aside: str | None = None) -> dict[str, object]:
    turn: dict[str, object] = {"segments": [_segment(char) for char in hanzi]}
    if english_aside is not None:
        turn["english_aside"] = english_aside
    return turn


class Responder:
    """A FunctionModel callback returning ``turns`` in order, one per call.

    Records the messages each call received so a follow-up turn can assert it
    saw the prior turn's conversation.
    """

    # FunctionModel reads ``.__name__`` off its callback for the model name.
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


def _user_prompt_texts(messages: Sequence[ModelMessage]) -> list[str]:
    from pydantic_ai.messages import UserPromptPart

    return [
        part.content
        for message in messages
        for part in getattr(message, "parts", [])
        if isinstance(part, UserPromptPart) and isinstance(part.content, str)
    ]


def _system_prompt_texts(messages: Sequence[ModelMessage]) -> list[str]:
    from pydantic_ai.messages import SystemPromptPart

    return [
        part.content
        for message in messages
        for part in getattr(message, "parts", [])
        if isinstance(part, SystemPromptPart) and isinstance(part.content, str)
    ]


def test_get_practice_agent_returns_the_module_agent() -> None:
    # Trivial + argument-free so dependency_overrides can swap it wholesale.
    assert practice_chat.get_practice_agent() is practice_chat._practice_agent


@pytest.mark.anyio
async def test_run_practice_turn_returns_turn_and_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    respond = Responder([_turn("你好", "你想聊什么")])
    monkeypatch.setattr(practice_chat, "_build_model", lambda: FunctionModel(respond))

    result = await run_practice_turn(
        practice_chat.get_practice_agent(), message="ordering food"
    )

    assert isinstance(result.turn, PracticeTurn)
    assert [segment.hanzi for segment in result.turn.segments] == ["你好", "你想聊什么"]
    assert result.turn.english_aside is None
    # The full conversation is returned for the caller to hand to the client.
    assert result.messages
    # Only this turn's prompt reached the model — no prior conversation.
    assert _user_prompt_texts(respond.messages_per_call[0]) == ["ordering food"]


@pytest.mark.anyio
async def test_follow_up_turn_receives_prior_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    respond = Responder([_turn("你好"), _turn("我很好")])
    monkeypatch.setattr(practice_chat, "_build_model", lambda: FunctionModel(respond))
    agent = practice_chat.get_practice_agent()

    first = await run_practice_turn(agent, message="ordering food")
    second = await run_practice_turn(agent, message="你好吗", history=first.messages)

    assert [segment.hanzi for segment in second.turn.segments] == ["我很好"]
    # The follow-up turn's model call actually saw the first turn's prompt.
    prompts = _user_prompt_texts(respond.messages_per_call[1])
    assert any("ordering food" in text for text in prompts)
    assert any("你好吗" in text for text in prompts)


@pytest.mark.anyio
async def test_english_aside_round_trips_when_model_fills_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The break-glass channel is just a field: when the model fills it, it
    # arrives on the structured turn alongside the Chinese segments.
    respond = Responder(
        [_turn("我们继续吧", english_aside="它 means 'it' — used for things.")]
    )
    monkeypatch.setattr(practice_chat, "_build_model", lambda: FunctionModel(respond))

    result = await run_practice_turn(
        practice_chat.get_practice_agent(), message="what does 它 mean?"
    )

    assert result.turn.english_aside == "它 means 'it' — used for things."
    assert [segment.hanzi for segment in result.turn.segments] == ["我们继续吧"]


@pytest.mark.anyio
async def test_tutor_system_prompt_reaches_model() -> None:
    respond = Responder([_turn("你好")])

    await practice_chat.get_practice_agent().run(
        "ordering food", model=FunctionModel(respond)
    )

    joined = "\n".join(_system_prompt_texts(respond.messages_per_call[0]))
    # The tutor persona and the structured-turn instructions made it through.
    assert "conversation partner" in joined
    assert "english_aside" in joined
    assert "HSK 1-2" in joined


def test_build_model_raises_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(practice_chat.settings, "openrouter_api_key", "")

    assert practice_chat.settings.practice_configured is False
    with pytest.raises(PracticeNotConfiguredError):
        practice_chat._build_model()


def test_build_model_uses_the_practice_model_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # PRACTICE_MODEL is independent of GENERATION_MODEL, so chat can run a
    # different model than pack drafting.
    monkeypatch.setattr(practice_chat.settings, "openrouter_api_key", "sk-test")
    monkeypatch.setattr(practice_chat.settings, "practice_model", "qwen/qwen-chat")
    monkeypatch.setattr(
        practice_chat.settings, "generation_model", "deepseek/deepseek-v4-flash"
    )

    model = practice_chat._build_model()

    # Built against OpenRouter with the practice model; no request is made.
    assert isinstance(model, OpenAIChatModel)
    assert model.model_name == "qwen/qwen-chat"
    assert model.system == "openrouter"
    assert "openrouter" in model.base_url
