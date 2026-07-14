"""Unit tests for the pack-generation grounding logic (Epic 7).

No network and no database: the corpus is a lightweight in-memory stub that
mimics :class:`~habagou.repositories.characters.CharacterRepository`'s
membership and stroke-count queries.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from habagou.dtos.generation import PackDraft
from habagou.services.pack_generation import (
    CorpusCheck,
    GenerationDeps,
    find_characters,
    validate_corpus_membership,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from pydantic_ai.messages import ModelMessage


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
