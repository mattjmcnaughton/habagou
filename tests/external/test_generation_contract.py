"""Live-provider contract test for pack generation (HAB-087).

One real round trip against the configured OpenRouter model, to catch drift in
the prompt, the output schema, or the model's ability to ground itself through
the ``find_characters`` tool + output-validator loop. It is the only test that
actually calls a provider, so it is quarantined in ``tests/external/`` (never
collected by ``just gate`` / ``test-unit`` / ``test-integration`` / ``test-e2e``,
which target the other ``tests/*`` directories) and gated behind
``@pytest.mark.external`` — reachable only via ``just test-external``.

Keyless-safe: it skips cleanly when ``OPENROUTER_API_KEY`` is unset, so the
target can be invoked without credentials. When a key is present it locally
lifts the suite-wide ``ALLOW_MODEL_REQUESTS`` guard with
``override_allow_model_requests(True)``. ``just test-external`` also sets the
test-only opt-in that prevents ``tests/conftest.py`` from scrubbing the key.

No database: the corpus seam is an in-memory stub (mirroring the ``StubCorpus``
pattern in ``tests/unit/test_pack_generation.py``) seeded with a realistic set
of common hanzi and plausible stroke counts. The real module agent and the real
``_build_model()`` output run against it, proving the model grounds every
drafted glyph through the tool + validator against a live provider.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pydantic_ai.models import override_allow_model_requests

from habagou.agents.generation import GenerationDeps
from habagou.config import settings
from habagou.dtos.generation import PackDraft
from habagou.services.pack_generation import (
    _build_model,
    get_generation_agent,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

# A realistic slice of common hanzi with real stroke counts, weighted toward the
# restaurant/food topic so the model has genuine material to ground a pack in.
_CORPUS_STROKES: dict[str, int] = {
    "你": 7,
    "好": 6,
    "我": 7,
    "他": 5,
    "谢": 12,
    "请": 10,
    "不": 4,
    "是": 9,
    "有": 6,
    "的": 8,
    "要": 9,
    "吃": 6,
    "喝": 12,
    "米": 6,
    "饭": 7,
    "茶": 9,
    "水": 4,
    "鱼": 8,
    "菜": 11,
    "肉": 6,
    "蛋": 11,
    "面": 9,
    "包": 5,
    "点": 9,
    "杯": 8,
    "多": 6,
    "少": 4,
    "钱": 10,
    "个": 3,
    "人": 2,
    "很": 9,
    "大": 3,
    "小": 3,
    "中": 4,
    "一": 1,
    "二": 2,
    "三": 3,
}


class _StubCorpus:
    """In-memory corpus seam: known hanzi mapped to their stroke counts.

    Mirrors ``CharacterRepository``'s membership/stroke-count queries so the
    grounding tool and output validator run with no database.
    """

    def __init__(self, strokes: dict[str, int]) -> None:
        self._strokes = strokes

    async def missing_hanzi(self, hanzi: Iterable[str]) -> set[str]:
        return {char for char in set(hanzi) if char not in self._strokes}

    async def stroke_counts(self, hanzi: Iterable[str]) -> dict[str, int]:
        return {
            char: self._strokes[char] for char in set(hanzi) if char in self._strokes
        }

    async def all_hanzi(self) -> tuple[str, ...]:
        return tuple(sorted(self._strokes))


def _drafted_glyphs(draft: PackDraft) -> set[str]:
    """Every glyph the draft would trace: members plus each sentence glyph."""
    glyphs = {character.hanzi for character in draft.characters}
    for sentence in draft.sentences:
        glyphs.update(char for char in sentence.hanzi if char.strip())
    return glyphs


@pytest.mark.external
@pytest.mark.anyio
async def test_live_provider_grounds_pack_in_corpus() -> None:
    if not settings.openrouter_api_key:
        pytest.skip("OPENROUTER_API_KEY is unset; skipping live provider contract test")

    deps = GenerationDeps(characters=_StubCorpus(_CORPUS_STROKES))
    agent = get_generation_agent()

    with override_allow_model_requests(True):
        result = await agent.run(
            "ordering food at a restaurant",
            deps=deps,
            model=_build_model(),
        )

    draft = result.output
    # The output schema still binds: a well-formed PackDraft came back.
    assert isinstance(draft, PackDraft)
    assert len(draft.characters) >= 1
    # Every drafted glyph — members and each glyph inside every sentence — is in
    # the corpus, proving the model grounded itself through the tool + validator
    # loop end to end against the live model.
    unknown = _drafted_glyphs(draft) - set(_CORPUS_STROKES)
    assert not unknown, f"model drafted non-corpus glyphs: {sorted(unknown)}"
