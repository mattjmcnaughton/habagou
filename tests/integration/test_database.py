from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from habagou.db import async_session
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


@pytest.mark.anyio
async def test_database_round_trips_pack_and_completion() -> None:
    async with async_session() as session:
        user = User(username="schema-test", display_name="Schema Test", is_guest=False)
        ni = Character(
            hanzi="你",
            stroke_data={"strokes": ["M 0 0"], "medians": [[[0, 0], [1, 1]]]},
            stroke_count=1,
        )
        hao = Character(
            hanzi="好",
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
    assert [link.character.hanzi for link in saved.characters] == ["你", "好"]
    assert saved.characters[0].pinyin == "nǐ"
    assert saved.sentences[0].hanzi == "你好"
    assert saved.completions[0].activity is ActivityType.TRACE
    assert saved.completions[0].duration_ms == 1234
