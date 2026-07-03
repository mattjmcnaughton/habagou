from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from habagou import db
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
from scripts.seed import (
    GUEST_USER_ID,
    SEED_PACKS,
    MissingCharactersError,
    SeedCharacter,
    SeedPack,
    SeedSentence,
    seed_database,
)


@pytest.mark.anyio
async def test_database_round_trips_pack_and_completion() -> None:
    async with db.async_session() as session:
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

    async with db.async_session() as session:
        result = await session.execute(
            select(Character).where(Character.hanzi.in_(source_records))
        )
        rows = {character.hanzi: character for character in result.scalars()}

    assert rows.keys() == source_records.keys()
    for hanzi, source in source_records.items():
        assert rows[hanzi].stroke_data == source.stroke_data
        assert rows[hanzi].stroke_count == source.stroke_count


@pytest.mark.workflow("WF-01")
@pytest.mark.anyio
async def test_seed_database_is_idempotent() -> None:
    await seed_database()
    await seed_database()

    seed_slugs = [pack.slug for pack in SEED_PACKS]
    async with db.async_session() as session:
        guest_count = await session.scalar(
            select(func.count()).select_from(User).where(User.username == "guest")
        )
        guest = await session.scalar(select(User).where(User.username == "guest"))
        result = await session.execute(
            select(Pack)
            .where(Pack.slug.in_(seed_slugs))
            .order_by(Pack.sort_order)
            .options(
                selectinload(Pack.characters).selectinload(PackCharacter.character),
                selectinload(Pack.sentences),
            )
        )
        packs = result.scalars().all()
        seeded_pack_ids = [pack.id for pack in packs]
        character_count = await session.scalar(
            select(func.count())
            .select_from(PackCharacter)
            .where(PackCharacter.pack_id.in_(seeded_pack_ids))
        )
        sentence_count = await session.scalar(
            select(func.count())
            .select_from(PackSentence)
            .where(PackSentence.pack_id.in_(seeded_pack_ids))
        )

    assert guest_count == 1
    assert guest is not None
    assert guest.id == GUEST_USER_ID
    assert guest.display_name == "Guest"
    assert guest.is_guest is True

    assert [pack.slug for pack in packs] == seed_slugs
    assert [pack.title for pack in packs] == [
        "Greetings",
        "Numbers",
        "Family",
        "Food & drink",
    ]
    assert [pack.status for pack in packs] == [PackStatus.PUBLISHED] * 4
    assert character_count == sum(len(pack.characters) for pack in SEED_PACKS)
    assert sentence_count == sum(len(pack.sentences) for pack in SEED_PACKS)

    for saved, expected in zip(packs, SEED_PACKS, strict=True):
        assert saved.title == expected.title
        assert saved.glyph == expected.glyph
        assert saved.color == expected.color
        assert [link.character.hanzi for link in saved.characters] == [
            character.hanzi for character in expected.characters
        ]
        assert [link.pinyin for link in saved.characters] == [
            character.pinyin for character in expected.characters
        ]
        assert [sentence.hanzi for sentence in saved.sentences] == [
            sentence.hanzi for sentence in expected.sentences
        ]


@pytest.mark.workflow("WF-01")
@pytest.mark.anyio
async def test_seed_validation_aborts_when_referenced_character_is_missing() -> None:
    broken_pack = SeedPack(
        slug="broken-pack",
        title="Broken pack",
        glyph="☂",
        color="#000000",
        sort_order=99,
        characters=(SeedCharacter("☂", "fake", "fake"),),
        sentences=(SeedSentence("☂", "fake", "fake"),),
    )

    async with db.async_session() as session:
        guest_count_before = await session.scalar(
            select(func.count()).select_from(User).where(User.username == "guest")
        )
        broken_pack_count_before = await session.scalar(
            select(func.count()).select_from(Pack).where(Pack.slug == "broken-pack")
        )

    with pytest.raises(MissingCharactersError, match="☂") as error:
        await seed_database((broken_pack,))

    async with db.async_session() as session:
        guest_count_after = await session.scalar(
            select(func.count()).select_from(User).where(User.username == "guest")
        )
        broken_pack_count_after = await session.scalar(
            select(func.count()).select_from(Pack).where(Pack.slug == "broken-pack")
        )

    assert error.value.missing == ("☂",)
    assert guest_count_after == guest_count_before
    assert broken_pack_count_after == broken_pack_count_before
