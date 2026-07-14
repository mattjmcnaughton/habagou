"""Unit tests for the pack-generation grounding logic (Epic 7).

No network and no database: the corpus is a lightweight in-memory stub that
mimics :class:`~habagou.repositories.characters.CharacterRepository`'s
membership and stroke-count queries.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

import pytest
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.models.test import TestModel

from habagou.dtos.generation import PackDraft
from habagou.services import pack_generation
from habagou.services.pack_generation import (
    CorpusCheck,
    GenerationDeps,
    GenerationNotConfiguredError,
    find_characters,
    validate_corpus_membership,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from pydantic_ai.messages import ModelMessage
    from sqlalchemy.ext.asyncio import AsyncSession


class StubCorpus:
    """In-memory corpus seam: known hanzi mapped to their stroke counts."""

    def __init__(self, strokes: dict[str, int]) -> None:
        self._strokes = strokes

    async def missing_hanzi(self, hanzi: Iterable[str]) -> set[str]:
        return {char for char in set(hanzi) if char not in self._strokes}

    async def stroke_counts(self, hanzi: Iterable[str]) -> dict[str, int]:
        return {
            char: self._strokes[char] for char in set(hanzi) if char in self._strokes
        }


def _deps(strokes: dict[str, int]) -> GenerationDeps:
    return GenerationDeps(characters=StubCorpus(strokes))


@pytest.mark.anyio
async def test_find_characters_reports_membership_and_stroke_counts() -> None:
    deps = _deps({"你": 7, "好": 6})

    result = await find_characters(deps, ["你", "好", "☂"])

    assert isinstance(result, CorpusCheck)
    # ``found`` carries stroke counts (a difficulty signal), not glosses.
    assert [(item.hanzi, item.stroke_count) for item in result.found] == [
        ("你", 7),
        ("好", 6),
    ]
    # Non-corpus candidates surface in ``dropped`` so the model avoids them.
    assert result.dropped == ["☂"]


@pytest.mark.anyio
async def test_find_characters_dedupes_and_preserves_input_order() -> None:
    deps = _deps({"你": 7, "好": 6, "我": 7})

    # Duplicates (including via a multi-char string) collapse to first-seen
    # order; multi-char strings are split into component characters.
    result = await find_characters(deps, ["我", "你好", "你", "我"])

    assert [item.hanzi for item in result.found] == ["我", "你", "好"]
    assert result.dropped == []


@pytest.mark.anyio
async def test_find_characters_splits_multichar_and_drops_non_corpus() -> None:
    deps = _deps({"你": 7, "好": 6})

    # "你X好" splits to 你 / X / 好; the middle char is not in the corpus.
    result = await find_characters(deps, ["你X好"])

    assert [item.hanzi for item in result.found] == ["你", "好"]
    assert result.dropped == ["X"]


@pytest.mark.anyio
async def test_find_characters_ignores_whitespace() -> None:
    deps = _deps({"你": 7, "好": 6})

    result = await find_characters(deps, ["你 好", "  "])

    assert [item.hanzi for item in result.found] == ["你", "好"]
    assert result.dropped == []


@pytest.mark.anyio
async def test_find_characters_empty_candidates() -> None:
    deps = _deps({"你": 7})

    result = await find_characters(deps, [])

    assert result.found == []
    assert result.dropped == []


# --- HAB-080: output validator -------------------------------------------------


def _character(hanzi: str) -> dict[str, str]:
    return {"hanzi": hanzi, "pinyin": "x", "meaning": "x"}


def _sentence(hanzi: str) -> dict[str, str]:
    return {"hanzi": hanzi, "pinyin": "x", "translation": "x"}


def _build_agent() -> Agent[GenerationDeps, PackDraft]:
    """A throwaway agent wiring the validator to ``RunContext.deps``."""
    agent = Agent[GenerationDeps, PackDraft](
        output_type=PackDraft,
        deps_type=GenerationDeps,
    )

    @agent.output_validator
    async def _validate(ctx: RunContext[GenerationDeps], draft: PackDraft) -> PackDraft:
        return await validate_corpus_membership(ctx.deps, draft)

    return agent


class Responder:
    """A FunctionModel callback returning ``drafts`` in order, one per call.

    Tracks ``call_count`` so tests can assert whether a retry happened.
    """

    # FunctionModel reads ``.__name__`` off its callback for the model name.
    __name__ = "responder"

    def __init__(self, drafts: list[dict[str, object]]) -> None:
        self._drafts = drafts
        self.call_count = 0

    def __call__(
        self, messages: Sequence[ModelMessage], info: AgentInfo
    ) -> ModelResponse:
        draft = self._drafts[self.call_count]
        self.call_count += 1
        tool_name = info.output_tools[0].name
        return ModelResponse(parts=[ToolCallPart(tool_name=tool_name, args=draft)])


@pytest.mark.anyio
async def test_validator_passes_valid_draft_through_unchanged() -> None:
    deps = _deps({"你": 7, "好": 6})
    draft = PackDraft.model_validate(
        {
            "title": "Greetings",
            "characters": [_character("你"), _character("好")],
            "sentences": [_sentence("你好")],
        }
    )

    result = await validate_corpus_membership(deps, draft)

    assert result is draft


@pytest.mark.anyio
async def test_validator_rejects_non_corpus_character() -> None:
    deps = _deps({"你": 7})
    draft = PackDraft.model_validate(
        {"title": "Bad", "characters": [_character("你"), _character("龘")]}
    )

    with pytest.raises(ModelRetry) as excinfo:
        await validate_corpus_membership(deps, draft)

    assert "龘" in str(excinfo.value)
    assert "你" not in str(excinfo.value)


@pytest.mark.anyio
async def test_validator_rejects_non_corpus_sentence_glyph() -> None:
    # Every glyph inside a sentence must be in the corpus, mirroring the seed
    # write path — even when all pack characters are valid.
    deps = _deps({"你": 7, "好": 6})
    draft = PackDraft.model_validate(
        {
            "title": "Sentence",
            "characters": [_character("你"), _character("好")],
            "sentences": [_sentence("你好龘")],
        }
    )

    with pytest.raises(ModelRetry) as excinfo:
        await validate_corpus_membership(deps, draft)

    assert "龘" in str(excinfo.value)


@pytest.mark.anyio
async def test_agent_retries_until_draft_is_corpus_valid() -> None:
    deps = _deps({"你": 7, "好": 6})
    agent = _build_agent()
    respond = Responder(
        [
            # First response references a non-corpus glyph -> ModelRetry.
            {"title": "First", "characters": [_character("你"), _character("龘")]},
            # Second response is fully grounded.
            {"title": "Second", "characters": [_character("你"), _character("好")]},
        ]
    )

    result = await agent.run("make a pack", deps=deps, model=FunctionModel(respond))

    # The retry happened (model called twice) and the valid draft won.
    assert respond.call_count == 2
    assert result.output.title == "Second"
    assert [c.hanzi for c in result.output.characters] == ["你", "好"]


@pytest.mark.anyio
async def test_agent_accepts_valid_draft_without_retry() -> None:
    deps = _deps({"你": 7, "好": 6})
    agent = _build_agent()
    respond = Responder(
        [{"title": "OK", "characters": [_character("你"), _character("好")]}]
    )

    result = await agent.run("make a pack", deps=deps, model=FunctionModel(respond))

    assert respond.call_count == 1
    assert result.output.title == "OK"


# --- HAB-081: assembled agent, model construction, service entry point ---------


class _ToolThenOutput:
    """Callback that calls find_characters, then emits ``output`` as the draft.

    Proves the grounding tool is actually registered on the real agent: on the
    second turn it records whether a ``find_characters`` tool return reached the
    model.
    """

    __name__ = "tool_then_output"

    def __init__(self, output: dict[str, object]) -> None:
        self._output = output
        self.call_count = 0
        self.saw_tool_return = False

    def __call__(
        self, messages: Sequence[ModelMessage], info: AgentInfo
    ) -> ModelResponse:
        self.call_count += 1
        if self.call_count == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="find_characters",
                        args={"candidates": ["你", "好", "龘"]},
                    )
                ]
            )
        for message in messages:
            for part in getattr(message, "parts", []):
                if (
                    isinstance(part, ToolReturnPart)
                    and part.tool_name == "find_characters"
                ):
                    self.saw_tool_return = True
        return ModelResponse(
            parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=self._output)]
        )


def test_get_generation_agent_returns_the_module_agent() -> None:
    # Trivial + argument-free so dependency_overrides can swap it wholesale.
    assert pack_generation.get_generation_agent() is pack_generation._generation_agent


@pytest.mark.anyio
async def test_real_agent_has_grounding_tool_wired() -> None:
    deps = _deps({"你": 7, "好": 6})
    agent = pack_generation.get_generation_agent()
    respond = _ToolThenOutput(
        {"title": "Grounded", "characters": [_character("你"), _character("好")]}
    )

    result = await agent.run("make a pack", deps=deps, model=FunctionModel(respond))

    # The model actually invoked find_characters and got a tool return back,
    # and the validated draft came through.
    assert respond.saw_tool_return is True
    assert result.output.title == "Grounded"


@pytest.mark.anyio
async def test_real_agent_output_validator_forces_retry() -> None:
    deps = _deps({"你": 7, "好": 6})
    agent = pack_generation.get_generation_agent()
    respond = Responder(
        [
            {"title": "First", "characters": [_character("你"), _character("龘")]},
            {"title": "Second", "characters": [_character("你"), _character("好")]},
        ]
    )

    result = await agent.run("make a pack", deps=deps, model=FunctionModel(respond))

    # The validator on the REAL assembled agent rejected the bad hanzi and the
    # model retried into a grounded draft.
    assert respond.call_count == 2
    assert result.output.title == "Second"


@pytest.mark.anyio
async def test_generate_pack_draft_returns_valid_draft_under_test_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corpus = StubCorpus({"你": 7, "好": 6})
    # Inject the corpus (no DB) and a TestModel producing a corpus-valid draft;
    # TestModel would otherwise synthesize hanzi the validator rejects.
    monkeypatch.setattr(pack_generation, "CharacterRepository", lambda _session: corpus)
    draft_args = {
        "title": "Greetings",
        "characters": [_character("你"), _character("好")],
        "sentences": [],
    }
    monkeypatch.setattr(
        pack_generation,
        "_build_model",
        lambda: TestModel(custom_output_args=draft_args),
    )

    result = await pack_generation.generate_pack_draft(
        pack_generation.get_generation_agent(),
        # The monkeypatched repository ignores the session entirely.
        session=cast("AsyncSession", object()),
        topic="greetings",
    )

    assert isinstance(result.draft, PackDraft)
    assert result.draft.title == "Greetings"
    assert [c.hanzi for c in result.draft.characters] == ["你", "好"]
    # The full conversation is returned for the caller to persist.
    assert result.messages


def test_build_model_raises_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pack_generation.settings, "openrouter_api_key", "")

    assert pack_generation.settings.generation_configured is False
    with pytest.raises(GenerationNotConfiguredError):
        pack_generation._build_model()


def test_build_model_builds_openrouter_model_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pack_generation.settings, "openrouter_api_key", "sk-test")
    monkeypatch.setattr(
        pack_generation.settings, "generation_model", "openai/gpt-5-mini"
    )

    model = pack_generation._build_model()

    # Built against OpenRouter with the configured model; no request is made.
    assert isinstance(model, OpenAIChatModel)
    assert model.model_name == "openai/gpt-5-mini"
    assert model.system == "openrouter"
    assert "openrouter" in model.base_url


# --- HAB-082: multi-turn message history ---------------------------------------


class _CapturingResponder:
    """Like :class:`Responder`, but records the messages seen on each call.

    Lets a test assert that a refinement turn's model callback actually receives
    the prior turn's conversation.
    """

    __name__ = "capturing_responder"

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


def _user_prompt_texts(messages: Sequence[ModelMessage]) -> list[str]:
    """Every user-prompt string across a message history (for assertions)."""
    from pydantic_ai.messages import UserPromptPart

    texts: list[str] = []
    for message in messages:
        for part in getattr(message, "parts", []):
            if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                texts.append(part.content)
    return texts


def _stub_session() -> AsyncSession:
    return cast("AsyncSession", object())


@pytest.mark.anyio
async def test_refinement_turn_receives_prior_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corpus = StubCorpus({"你": 7, "好": 6})
    monkeypatch.setattr(pack_generation, "CharacterRepository", lambda _session: corpus)
    respond = _CapturingResponder(
        [
            {"title": "First", "characters": [_character("你")]},
            {"title": "Second", "characters": [_character("你"), _character("好")]},
        ]
    )
    monkeypatch.setattr(pack_generation, "_build_model", lambda: FunctionModel(respond))
    agent = pack_generation.get_generation_agent()

    first = await pack_generation.generate_pack_draft(
        agent, session=_stub_session(), topic="greetings for beginners"
    )
    second = await pack_generation.generate_pack_draft(
        agent,
        session=_stub_session(),
        topic="make it harder",
        history=first.messages,
    )

    assert second.draft.title == "Second"
    # The refinement turn's model call actually saw the first turn's prompt.
    second_call_messages = respond.messages_per_call[1]
    prompts = _user_prompt_texts(second_call_messages)
    assert any("greetings for beginners" in text for text in prompts)
    assert any("make it harder" in text for text in prompts)


@pytest.mark.anyio
async def test_first_turn_without_history_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corpus = StubCorpus({"你": 7, "好": 6})
    monkeypatch.setattr(pack_generation, "CharacterRepository", lambda _session: corpus)
    respond = _CapturingResponder(
        [{"title": "Solo", "characters": [_character("你"), _character("好")]}]
    )
    monkeypatch.setattr(pack_generation, "_build_model", lambda: FunctionModel(respond))

    result = await pack_generation.generate_pack_draft(
        pack_generation.get_generation_agent(),
        session=_stub_session(),
        topic="greetings",
    )

    assert result.draft.title == "Solo"
    # Only this turn's prompt reached the model — no prior conversation.
    assert _user_prompt_texts(respond.messages_per_call[0]) == ["greetings"]


@pytest.mark.anyio
async def test_message_history_round_trips_through_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corpus = StubCorpus({"你": 7, "好": 6})
    monkeypatch.setattr(pack_generation, "CharacterRepository", lambda _session: corpus)
    respond = Responder(
        [{"title": "Trip", "characters": [_character("你"), _character("好")]}]
    )
    monkeypatch.setattr(pack_generation, "_build_model", lambda: FunctionModel(respond))

    result = await pack_generation.generate_pack_draft(
        pack_generation.get_generation_agent(),
        session=_stub_session(),
        topic="greetings",
    )

    dumped = pack_generation.dump_message_history(result.messages)
    # The dump is genuinely JSON-able (survives a JSON encode/decode cycle).
    assert json.loads(json.dumps(dumped)) == dumped
    # And it reconstructs the exact same messages.
    loaded = pack_generation.load_message_history(dumped)
    assert loaded == result.messages
