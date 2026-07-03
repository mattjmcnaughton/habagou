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

from habagou.db import async_session
from habagou.models import Character

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

CORPUS_VERSION = "v2.0.1"
CORPUS_URL = (
    "https://github.com/chanind/hanzi-writer-data/archive/refs/tags/"
    f"{CORPUS_VERSION}.tar.gz"
)
CORPUS_SHA256 = "be372ce1f0db677d609b707af804a0e603111f6efba7ab4b4a3a49cb99e48162"
CHUNK_SIZE = 500


@dataclass(frozen=True)
class StrokeRecord:
    hanzi: str
    stroke_data: dict[str, Any]
    stroke_count: int


def cache_dir() -> Path:
    root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return root / "habagou"


def archive_path() -> Path:
    return (
        cache_dir() / f"hanzi-writer-data-{CORPUS_VERSION}-{CORPUS_SHA256[:12]}.tar.gz"
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
        if actual != CORPUS_SHA256:
            raise RuntimeError(f"{path} has sha256 {actual}, expected {CORPUS_SHA256}")
        return path

    destination = archive_path()
    if destination.exists() and sha256(destination) == CORPUS_SHA256:
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    with (
        urllib.request.urlopen(CORPUS_URL, timeout=60) as response,
        NamedTemporaryFile(dir=destination.parent, delete=False) as tmp,
    ):
        tmp_path = Path(tmp.name)
        while chunk := response.read(1024 * 1024):
            tmp.write(chunk)

    actual = sha256(tmp_path)
    if actual != CORPUS_SHA256:
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"downloaded corpus sha256 {actual}, expected {CORPUS_SHA256}"
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
            if not member.isfile() or "/data/" not in member.name:
                continue
            hanzi = Path(member.name).stem
            if hanzi == "all":
                continue
            if subset is not None and hanzi not in subset:
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
    async with async_session() as session:
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
) -> tuple[int, int, float]:
    started_at = time.perf_counter()
    source = ensure_archive(archive)
    subset = read_subset(subset_path)
    records = list(iter_records(source, subset))
    changed = await import_records(records)
    return len(records), changed, time.perf_counter() - started_at


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--subset", type=Path, help="file containing fixture characters"
    )
    parser.add_argument("--archive", type=Path, help="pre-downloaded corpus archive")
    args = parser.parse_args()

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
