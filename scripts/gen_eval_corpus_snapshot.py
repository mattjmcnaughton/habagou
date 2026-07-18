"""Regenerate the eval harness's frozen corpus snapshot (evals/corpus_snapshot.json).

The eval harness (``evals/``, see ``docs/evals.md``) needs a ``CorpusReader``
with no database: corpus *membership* and *stroke counts* only, never
``stroke_data``. This script derives that snapshot from the same pinned
hanzi-writer-data archive that ``scripts/import_stroke_data.py`` imports into
Postgres — same ``CORPUS_VERSION``, same ``CORPUS_SHA256`` — so eval runs see
exactly the corpus production would.

The snapshot is committed; rerun this only when the pinned corpus version in
``import_stroke_data.py`` changes:

    uv run python scripts/gen_eval_corpus_snapshot.py
"""

from __future__ import annotations

import json
from pathlib import Path

from import_stroke_data import CORPUS_VERSION, ensure_archive, iter_records

SNAPSHOT_PATH = (
    Path(__file__).resolve().parent.parent / "evals" / "corpus_snapshot.json"
)


def main() -> None:
    archive = ensure_archive()
    strokes = {record.hanzi: record.stroke_count for record in iter_records(archive)}
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Codepoint-sorted keys keep the file diff-stable across regenerations.
    payload = {
        "corpus_version": CORPUS_VERSION,
        "stroke_counts": dict(sorted(strokes.items())),
    }
    SNAPSHOT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=None, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {SNAPSHOT_PATH}: {len(strokes)} characters ({CORPUS_VERSION})")


if __name__ == "__main__":
    main()
