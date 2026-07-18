"""Frozen corpus fixture: a database-free ``CorpusReader`` for eval runs.

``corpus_snapshot.json`` is a committed ``{hanzi: stroke_count}`` map derived
from the same pinned hanzi-writer-data archive that
``scripts/import_stroke_data.py`` loads into Postgres, so eval runs ground
against exactly the corpus production serves. Regenerate it with
``scripts/gen_eval_corpus_snapshot.py`` when the pinned corpus version bumps.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

SNAPSHOT_PATH = Path(__file__).resolve().parent / "corpus_snapshot.json"


class SnapshotCorpus:
    """In-memory corpus seam over the frozen snapshot.

    Structurally satisfies :class:`habagou.agents.generation.CorpusReader`,
    mirroring ``CharacterRepository``'s membership/stroke-count queries so the
    grounding tool and output validator run with no database.
    """

    def __init__(self, stroke_counts: dict[str, int]) -> None:
        self._strokes = stroke_counts
        # Codepoint-sorted, like CharacterRepository.all_hanzi, so the corpus
        # block in the system prompt is deterministic.
        self._all_hanzi = tuple(sorted(stroke_counts))

    async def missing_hanzi(self, hanzi: Iterable[str]) -> set[str]:
        return {char for char in set(hanzi) if char not in self._strokes}

    async def stroke_counts(self, hanzi: Iterable[str]) -> dict[str, int]:
        return {
            char: self._strokes[char] for char in set(hanzi) if char in self._strokes
        }

    async def all_hanzi(self) -> tuple[str, ...]:
        return self._all_hanzi


@cache
def _stroke_counts() -> dict[str, int]:
    payload = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    return payload["stroke_counts"]


@cache
def corpus_hanzi() -> frozenset[str]:
    """Every traceable hanzi in the snapshot, for evaluator membership checks."""
    return frozenset(_stroke_counts())


def snapshot_corpus() -> SnapshotCorpus:
    """A fresh ``CorpusReader`` over the committed snapshot."""
    return SnapshotCorpus(_stroke_counts())
