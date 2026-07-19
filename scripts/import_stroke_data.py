"""Import pinned hanzi-writer-data into Postgres."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import tarfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy.dialects.postgresql import insert

from habagou import db
from habagou.models import Character

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

CORPUS_VERSION = "v2.0.1"


@dataclass(frozen=True)
class CorpusSource:
    """One pinned, content-addressed mirror of the corpus release."""

    name: str
    url: str
    sha256: str


# The same corpus release is published in two places: the GitHub tag archive
# and the immutable npm registry tarball. Both are pinned by sha256, so either
# yields byte-verified data; sources are tried in order. The npm mirror keeps
# bootstrap working in sandboxed/CI environments whose egress policy allows
# registry.npmjs.org but not github.com downloads.
CORPUS_SOURCES: tuple[CorpusSource, ...] = (
    CorpusSource(
        name="github",
        url=(
            "https://github.com/chanind/hanzi-writer-data/archive/refs/tags/"
            f"{CORPUS_VERSION}.tar.gz"
        ),
        sha256="be372ce1f0db677d609b707af804a0e603111f6efba7ab4b4a3a49cb99e48162",
    ),
    CorpusSource(
        name="npm",
        url=(
            "https://registry.npmjs.org/hanzi-writer-data/-/"
            f"hanzi-writer-data-{CORPUS_VERSION.lstrip('v')}.tgz"
        ),
        sha256="72baf3d82b114e60d6e40ea05f24d2262a05cd39d544e2f322ba2fceb7beff15",
    ),
)
CHUNK_SIZE = 500


@dataclass(frozen=True)
class StrokeRecord:
    hanzi: str
    stroke_data: dict[str, Any]
    stroke_count: int


def cache_dir() -> Path:
    root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return root / "habagou"


def archive_path(source: CorpusSource) -> Path:
    return (
        cache_dir() / f"hanzi-writer-data-{CORPUS_VERSION}-{source.sha256[:12]}.tar.gz"
    )


def cached_archive() -> Path:
    """Return the first cached, sha-verified corpus archive.

    Raises when no verified archive is cached; callers that must not download
    (the integration test harness) use this to fail fast with a pointer to
    ``just bootstrap``, which populates the cache.
    """
    for source in CORPUS_SOURCES:
        candidate = archive_path(source)
        if candidate.exists() and sha256(candidate) == source.sha256:
            return candidate
    raise RuntimeError(
        "no verified corpus archive cached; run `just bootstrap` (or "
        "`python scripts/import_stroke_data.py`) first"
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_archive(path: Path | None = None) -> Path:
    if path is not None:
        actual = sha256(path)
        expected = {source.sha256 for source in CORPUS_SOURCES}
        if actual not in expected:
            raise RuntimeError(
                f"{path} has sha256 {actual}, expected one of {sorted(expected)}"
            )
        return path

    try:
        return cached_archive()
    except RuntimeError:
        pass

    failures: list[str] = []
    for source in CORPUS_SOURCES:
        try:
            return _download_source(source)
        except (OSError, RuntimeError) as error:
            failures.append(f"{source.name} ({source.url}): {error}")
    raise RuntimeError(
        "corpus download failed from every pinned source:\n"
        + "\n".join(f"  - {failure}" for failure in failures)
    )


def _download_source(source: CorpusSource) -> Path:
    destination = archive_path(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with (
        urllib.request.urlopen(source.url, timeout=60) as response,
        NamedTemporaryFile(dir=destination.parent, delete=False) as tmp,
    ):
        tmp_path = Path(tmp.name)
        while chunk := response.read(1024 * 1024):
            tmp.write(chunk)

    actual = sha256(tmp_path)
    if actual != source.sha256:
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"downloaded corpus sha256 {actual}, expected {source.sha256}"
        )

    tmp_path.replace(destination)
    return destination


def read_subset(path: Path | None) -> set[str] | None:
    if path is None:
        return None
    chars: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        chars.update(line)
    return chars


def iter_records(path: Path, subset: set[str] | None = None) -> Iterator[StrokeRecord]:
    seen: set[str] = set()
    with tarfile.open(path, "r:gz") as archive:
        for member in archive:
            # Corpus records are one JSON file per character in both source
            # layouts: `<prefix>/data/<hanzi>.json` (GitHub archive) and
            # `package/<hanzi>.json` (npm tarball). A single non-ASCII stem
            # identifies them and excludes all.json, package.json, and the
            # other package scaffolding in either layout.
            if not member.isfile() or not member.name.endswith(".json"):
                continue
            hanzi = Path(member.name).stem
            if len(hanzi) != 1 or hanzi.isascii():
                continue
            if subset is not None and hanzi not in subset:
                continue
            # A duplicate stem within one archive would make the batched
            # ON CONFLICT upsert touch the same row twice and fail.
            if hanzi in seen:
                continue

            extracted = archive.extractfile(member)
            if extracted is None:
                continue
            stroke_data = json.loads(extracted.read().decode("utf-8"))
            strokes = stroke_data.get("strokes")
            if not isinstance(strokes, list):
                raise ValueError(f"{member.name} has no strokes array")
            seen.add(hanzi)
            yield StrokeRecord(
                hanzi=hanzi,
                stroke_data=stroke_data,
                stroke_count=len(strokes),
            )

    if subset is not None:
        missing = sorted(subset - seen)
        if missing:
            raise ValueError(
                f"subset characters missing from corpus: {''.join(missing)}"
            )


def _chunks(records: Iterable[StrokeRecord], size: int) -> Iterator[list[StrokeRecord]]:
    batch: list[StrokeRecord] = []
    for record in records:
        batch.append(record)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


async def import_records(records: Iterable[StrokeRecord]) -> int:
    changed = 0
    async with db.async_session() as session:
        for batch in _chunks(records, CHUNK_SIZE):
            rows = [
                {
                    "hanzi": record.hanzi,
                    "stroke_data": record.stroke_data,
                    "stroke_count": record.stroke_count,
                }
                for record in batch
            ]
            statement = insert(Character).values(rows)
            excluded = statement.excluded
            statement = statement.on_conflict_do_update(
                index_elements=[Character.hanzi],
                set_={
                    "stroke_data": excluded.stroke_data,
                    "stroke_count": excluded.stroke_count,
                },
                where=Character.stroke_data.is_distinct_from(excluded.stroke_data)
                | Character.stroke_count.is_distinct_from(excluded.stroke_count),
            )
            result = await session.execute(statement)
            changed += cast("Any", result).rowcount
        await session.commit()
    return changed


async def import_corpus(
    *,
    archive: Path | None = None,
    subset_path: Path | None = None,
    subset: set[str] | None = None,
) -> tuple[int, int, float]:
    """Import the corpus, optionally restricted to a subset of characters.

    ``subset_path`` and ``subset`` compose (union) so callers can combine a
    fixture file with programmatically derived characters; both omitted means
    the full corpus.
    """
    started_at = time.perf_counter()
    source = ensure_archive(archive)
    combined = read_subset(subset_path)
    if subset is not None:
        combined = subset if combined is None else combined | subset
    records = list(iter_records(source, combined))
    changed = await import_records(records)
    return len(records), changed, time.perf_counter() - started_at


def write_index(archive: Path, destination: Path) -> int:
    """Write the sorted hanzi of the full corpus, one per line.

    The committed index (``data/corpus_index.txt``) lets pack-data validation
    run without a database or network; regenerate it with ``--write-index``
    whenever the pinned corpus version changes.
    """
    hanzi = sorted(record.hanzi for record in iter_records(archive))
    destination.write_text("".join(f"{char}\n" for char in hanzi), encoding="utf-8")
    return len(hanzi)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--subset", type=Path, help="file containing fixture characters"
    )
    parser.add_argument("--archive", type=Path, help="pre-downloaded corpus archive")
    parser.add_argument(
        "--write-index",
        type=Path,
        help="write the corpus hanzi index to this path and exit (no import)",
    )
    args = parser.parse_args()

    if args.write_index is not None:
        count = write_index(ensure_archive(args.archive), args.write_index)
        print(f"corpus index written: version={CORPUS_VERSION} chars={count}")
        return

    total, changed, elapsed = asyncio.run(
        import_corpus(archive=args.archive, subset_path=args.subset)
    )
    print(
        "stroke corpus import completed: "
        f"version={CORPUS_VERSION} total={total} changed={changed} "
        f"elapsed={elapsed:.1f}s"
    )


if __name__ == "__main__":
    main()
