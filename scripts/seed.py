"""Seed prototype learning packs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import delete, select

from habagou import db
from habagou.events import emit_workflow_event
from habagou.models import (
    Character,
    Pack,
    PackCharacter,
    PackSentence,
    PackStatus,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class SeedCharacter:
    hanzi: str
    pinyin: str
    meaning: str


@dataclass(frozen=True)
class SeedSentence:
    hanzi: str
    pinyin: str
    translation: str


@dataclass(frozen=True)
class SeedPack:
    slug: str
    title: str
    glyph: str
    color: str
    sort_order: int
    characters: tuple[SeedCharacter, ...]
    sentences: tuple[SeedSentence, ...]


@dataclass(frozen=True)
class SeedResult:
    chars: int
    packs: int


class MissingCharactersError(RuntimeError):
    """Raised when seed data references characters absent from the corpus."""

    def __init__(self, missing: Iterable[str]) -> None:
        self.missing = tuple(sorted(missing))
        super().__init__(
            "seed data references characters missing from corpus: "
            f"{''.join(self.missing)}"
        )


SEED_PACKS: tuple[SeedPack, ...] = (
    SeedPack(
        slug="greetings",
        title="Greetings",
        glyph="你",
        color="#c4633f",
        sort_order=1,
        characters=(
            SeedCharacter("你", "nǐ", "you"),
            SeedCharacter("好", "hǎo", "good"),
            SeedCharacter("我", "wǒ", "I, me"),
            SeedCharacter("他", "tā", "he, him"),
            SeedCharacter("谢", "xiè", "thanks"),
        ),
        sentences=(
            SeedSentence("你好", "nǐ hǎo", "Hello"),
            SeedSentence("我很好", "wǒ hěn hǎo", "I am well"),
            SeedSentence("谢谢你", "xièxie nǐ", "Thank you"),
        ),
    ),
    SeedPack(
        slug="numbers",
        title="Numbers",
        glyph="三",
        color="#3f8a86",
        sort_order=2,
        characters=(
            SeedCharacter("一", "yī", "one"),
            SeedCharacter("二", "èr", "two"),
            SeedCharacter("三", "sān", "three"),
            SeedCharacter("四", "sì", "four"),
            SeedCharacter("五", "wǔ", "five"),
        ),
        sentences=(
            SeedSentence("一二三", "yī èr sān", "One two three"),
            SeedSentence("三个人", "sān ge rén", "Three people"),
        ),
    ),
    SeedPack(
        slug="family",
        title="Family",
        glyph="妈",
        color="#5b5fa8",
        sort_order=3,
        characters=(
            SeedCharacter("妈", "mā", "mom"),
            SeedCharacter("爸", "bà", "dad"),
            SeedCharacter("哥", "gē", "older brother"),
            SeedCharacter("姐", "jiě", "older sister"),
            SeedCharacter("弟", "dì", "younger brother"),
        ),
        sentences=(
            SeedSentence("爸爸", "bàba", "Dad"),
            SeedSentence("我哥哥", "wǒ gēge", "My older brother"),
        ),
    ),
    SeedPack(
        slug="food-drink",
        title="Food & drink",
        glyph="茶",
        color="#b5852e",
        sort_order=4,
        characters=(
            SeedCharacter("米", "mǐ", "rice"),
            SeedCharacter("饭", "fàn", "meal"),
            SeedCharacter("茶", "chá", "tea"),
            SeedCharacter("水", "shuǐ", "water"),
            SeedCharacter("鱼", "yú", "fish"),
        ),
        sentences=(
            SeedSentence("米饭", "mǐfàn", "Cooked rice"),
            SeedSentence("喝茶", "hē chá", "Drink tea"),
        ),
    ),
)


def required_hanzi(packs: Sequence[SeedPack] = SEED_PACKS) -> set[str]:
    chars: set[str] = set()
    for pack in packs:
        chars.update(character.hanzi for character in pack.characters)
        for sentence in pack.sentences:
            chars.update(sentence.hanzi)
    return chars


async def load_characters(
    session: AsyncSession, chars: Iterable[str]
) -> dict[str, Character]:
    result = await session.execute(select(Character).where(Character.hanzi.in_(chars)))
    return {character.hanzi: character for character in result.scalars()}


async def validate_required_characters(
    session: AsyncSession,
    chars: Iterable[str] | None = None,
) -> dict[str, Character]:
    required = set(chars or required_hanzi())
    characters = await load_characters(session, required)
    missing = required - characters.keys()
    if missing:
        raise MissingCharactersError(missing)
    return characters


async def upsert_pack(
    session: AsyncSession,
    seed_pack: SeedPack,
    characters: dict[str, Character],
) -> None:
    result = await session.execute(select(Pack).where(Pack.slug == seed_pack.slug))
    pack = result.scalar_one_or_none()
    if pack is None:
        pack = Pack(slug=seed_pack.slug)
        session.add(pack)

    pack.title = seed_pack.title
    pack.glyph = seed_pack.glyph
    pack.color = seed_pack.color
    pack.status = PackStatus.PUBLISHED
    pack.sort_order = seed_pack.sort_order
    await session.flush()

    await session.execute(delete(PackCharacter).where(PackCharacter.pack_id == pack.id))
    await session.execute(delete(PackSentence).where(PackSentence.pack_id == pack.id))
    await session.flush()

    session.add_all(
        PackCharacter(
            pack_id=pack.id,
            character_id=characters[seed_character.hanzi].id,
            position=index,
            pinyin=seed_character.pinyin,
            meaning=seed_character.meaning,
        )
        for index, seed_character in enumerate(seed_pack.characters, start=1)
    )
    session.add_all(
        PackSentence(
            pack_id=pack.id,
            position=index,
            hanzi=seed_sentence.hanzi,
            pinyin=seed_sentence.pinyin,
            translation=seed_sentence.translation,
        )
        for index, seed_sentence in enumerate(seed_pack.sentences, start=1)
    )


async def seed_database(packs: Sequence[SeedPack] = SEED_PACKS) -> SeedResult:
    async with db.async_session() as session:
        required = required_hanzi(packs)
        characters = await validate_required_characters(session, required)
        for seed_pack in packs:
            await upsert_pack(session, seed_pack, characters)
        await session.commit()
    return SeedResult(chars=len(required), packs=len(packs))


def format_bootstrap_completed(result: SeedResult) -> str:
    return f"bootstrap_completed chars={result.chars} packs={result.packs}"


def emit_bootstrap_completed(
    result: SeedResult, *, migrations_applied: bool = True
) -> None:
    """Emit the canonical bootstrap workflow event."""
    emit_workflow_event(
        "bootstrap_completed",
        workflow="WF-01",
        chars_imported=result.chars,
        packs_seeded=result.packs,
        migrations_applied=migrations_applied,
    )


def main() -> None:
    result = asyncio.run(seed_database())
    emit_bootstrap_completed(result)
    print(format_bootstrap_completed(result))


if __name__ == "__main__":
    main()
