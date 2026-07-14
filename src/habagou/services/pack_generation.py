"""Grounding pieces for the agent pack-generation flow (Epic 7).

A generated pack may only contain hanzi that already live in the stroke corpus
(the ``characters`` table stores ``hanzi``/``stroke_data``/``stroke_count`` and
*no* glosses). The grounding logic keeps the model honest about that.

Layer 1 — :func:`find_characters`: a tool the model calls to learn which of its
candidate hanzi actually exist in the corpus (and how many strokes each takes, a
difficulty signal). It returns corpus *membership only*: the corpus has no
pinyin/meaning, so the model supplies every gloss itself.

The grounding logic takes a :class:`GenerationDeps` directly (not a
``RunContext``) so it is unit-testable without an agent or a database; the agent
assembly wires it to ``RunContext.deps`` in the next batch.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel

if TYPE_CHECKING:
    from collections.abc import Iterable


class CorpusReader(Protocol):
    """The corpus-membership seam the grounding logic depends on.

    :class:`~habagou.repositories.characters.CharacterRepository` satisfies it
    structurally; unit tests supply a lightweight stub so no database is needed.
    """

    async def missing_hanzi(self, hanzi: Iterable[str]) -> set[str]: ...

    async def stroke_counts(self, hanzi: Iterable[str]) -> dict[str, int]: ...


@dataclass(frozen=True)
class GenerationDeps:
    """Dependencies carried into the grounding tool and output validator.

    Holds the corpus seam rather than a raw session so the logic is testable
    against a stub. The agent wires a real ``CharacterRepository`` here.
    """

    characters: CorpusReader


class FoundCharacter(BaseModel):
    """A candidate confirmed to exist in the corpus, with its stroke count."""

    hanzi: str
    stroke_count: int


class CorpusCheck(BaseModel):
    """Result of :func:`find_characters`: corpus MEMBERSHIP only.

    The corpus stores no pinyin/meaning, so this reports nothing but which
    candidates exist (``found``, each with its ``stroke_count`` difficulty
    signal) and which do not (``dropped``). The model must supply every gloss
    itself. Both lists preserve first-seen input order for determinism.
    """

    found: list[FoundCharacter]
    dropped: list[str]


def _unique_characters(candidates: Iterable[str]) -> list[str]:
    """Flatten candidates to individual, deduped hanzi in first-seen order.

    Multi-character strings are split into their component characters (a pack
    traces one glyph at a time, and sentence tracing traces each glyph too), and
    whitespace is dropped. Duplicates collapse to their first appearance.
    """
    seen: set[str] = set()
    ordered: list[str] = []
    for candidate in candidates:
        for char in candidate:
            if char.strip() and char not in seen:
                seen.add(char)
                ordered.append(char)
    return ordered


async def find_characters(deps: GenerationDeps, candidates: list[str]) -> CorpusCheck:
    """Report which candidate hanzi exist in the stroke corpus (layer 1 tool).

    Candidates are normalized (multi-char strings split, whitespace dropped,
    deduped, order preserved). ``found`` carries each existing hanzi with its
    stroke count; ``dropped`` surfaces the candidates absent from the corpus so
    the model learns to avoid them. Returns membership only — never glosses.
    """
    ordered = _unique_characters(candidates)
    if not ordered:
        return CorpusCheck(found=[], dropped=[])

    missing = await deps.characters.missing_hanzi(ordered)
    present = [char for char in ordered if char not in missing]
    dropped = [char for char in ordered if char in missing]

    counts = await deps.characters.stroke_counts(present)
    found = [
        FoundCharacter(hanzi=char, stroke_count=counts[char])
        for char in present
        if char in counts
    ]
    return CorpusCheck(found=found, dropped=dropped)
