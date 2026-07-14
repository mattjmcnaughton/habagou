"""Unit tests for the pack-generation grounding logic (Epic 7).

No network and no database: the corpus is a lightweight in-memory stub that
mimics :class:`~habagou.repositories.characters.CharacterRepository`'s
membership and stroke-count queries.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from habagou.services.pack_generation import (
    CorpusCheck,
    GenerationDeps,
    find_characters,
)

if TYPE_CHECKING:
    from collections.abc import Iterable


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
