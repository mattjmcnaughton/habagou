from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from habagou.db import async_session, engine
from habagou.models import (
    ActivityCompletion,
    ActivityType,
    Character,
    Pack,
    PackCharacter,
    PackSentence,
    PackStatus,
    User,
)
from scripts.import_stroke_data import (
    archive_path,
    ensure_archive,
    import_corpus,
    iter_records,
    read_subset,
)


@pytest.fixture(autouse=True)
async def dispose_engine_after_test():
    yield
    await engine.dispose()


@pytest.mark.anyio
async def test_database_round_trips_pack_and_completion() -> None:
    async with async_session() as session:
        user = User(username="schema-test", display_name="Schema Test", is_guest=False)
        ni = Character(
            hanzi="☀",
            stroke_data={"strokes": ["M 0 0"], "medians": [[[0, 0], [1, 1]]]},
            stroke_count=1,
        )
        hao = Character(
            hanzi="☁",
            stroke_data={"strokes": ["M 1 1"], "medians": [[[1, 1], [2, 2]]]},
            stroke_count=1,
        )
        pack = Pack(
            slug="schema-test",
            title="Schema Test",
            glyph="你",
            color="#5fb89a",
            status=PackStatus.PUBLISHED,
            sort_order=1,
            characters=[
                PackCharacter(character=ni, position=1, pinyin="nǐ", meaning="you"),
                PackCharacter(character=hao, position=2, pinyin="hǎo", meaning="good"),
            ],
            sentences=[
                PackSentence(
                    position=1,
                    hanzi="你好",
                    pinyin="nǐ hǎo",
                    translation="hello",
                )
            ],
        )
        completion = ActivityCompletion(
            user=user,
            pack=pack,
            activity=ActivityType.TRACE,
            duration_ms=1234,
        )
        session.add_all([user, pack, completion])
        await session.commit()

        result = await session.execute(
            select(Pack)
            .where(Pack.slug == "schema-test")
            .options(
                selectinload(Pack.characters).selectinload(PackCharacter.character),
                selectinload(Pack.sentences),
                selectinload(Pack.completions),
            )
        )
        saved = result.scalar_one()

    assert saved.status is PackStatus.PUBLISHED
    assert [link.character.hanzi for link in saved.characters] == ["☀", "☁"]
    assert saved.characters[0].pinyin == "nǐ"
    assert saved.sentences[0].hanzi == "你好"
    assert saved.completions[0].activity is ActivityType.TRACE
    assert saved.completions[0].duration_ms == 1234


@pytest.mark.anyio
async def test_stroke_import_matches_fixture_subset() -> None:
    subset_path = Path("tests/fixtures/stroke_subset.txt")
    cached_archive = archive_path()
    if not cached_archive.exists():
        pytest.skip("stroke corpus archive is not cached; run `just bootstrap` first")

    total, _changed, _elapsed = await import_corpus(
        archive=cached_archive,
        subset_path=subset_path,
    )
    _rerun_total, rerun_changed, _rerun_elapsed = await import_corpus(
        archive=cached_archive, subset_path=subset_path
    )

    subset = read_subset(subset_path)
    assert subset is not None
    assert total == len(subset)
    assert rerun_changed == 0

    source_records = {
        record.hanzi: record
        for record in iter_records(ensure_archive(cached_archive), subset)
    }

    async with async_session() as session:
        result = await session.execute(
            select(Character).where(Character.hanzi.in_(source_records))
        )
        rows = {character.hanzi: character for character in result.scalars()}

    assert rows.keys() == source_records.keys()
    for hanzi, source in source_records.items():
        assert rows[hanzi].stroke_data == source.stroke_data
        assert rows[hanzi].stroke_count == source.stroke_count
