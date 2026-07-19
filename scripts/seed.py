"""Seed curated library categories and packs from ``data/packs/``."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import delete, select

from habagou import db
from habagou.events import emit_workflow_event
from habagou.models import (
    Category,
    Character,
    Pack,
    PackCharacter,
    PackSentence,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

PACK_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "packs"


@dataclass(frozen=True)
class SeedCategory:
    slug: str
    title: str
    sort_order: int


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
    category: str
    description: str
    starter: bool
    sort_order: int
    characters: tuple[SeedCharacter, ...]
    sentences: tuple[SeedSentence, ...]


@dataclass(frozen=True)
class SeedResult:
    chars: int
    packs: int
    categories: int


class MissingCharactersError(RuntimeError):
    """Raised when seed data references characters absent from the corpus."""

    def __init__(self, missing: Iterable[str]) -> None:
        self.missing = tuple(sorted(missing))
        super().__init__(
            "seed data references characters missing from corpus: "
            f"{''.join(self.missing)}"
        )


def load_seed_categories(data_dir: Path = PACK_DATA_DIR) -> tuple[SeedCategory, ...]:
    raw = json.loads((data_dir / "categories.json").read_text(encoding="utf-8"))
    return tuple(
        SeedCategory(
            slug=entry["slug"],
            title=entry["title"],
            sort_order=entry["sort_order"],
        )
        for entry in raw
    )


def load_seed_packs(data_dir: Path = PACK_DATA_DIR) -> tuple[SeedPack, ...]:
    """Load every pack file under ``data/packs/<category>/<slug>.json``.

    Returned in ``sort_order`` order so downstream iteration (and the seeded
    curriculum) is deterministic. Schema and cross-file invariants are enforced
    by ``scripts/validate_pack_data.py`` in the gate; this loader only parses.
    """
    packs = []
    for path in sorted(data_dir.glob("*/*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        packs.append(
            SeedPack(
                slug=raw["slug"],
                title=raw["title"],
                glyph=raw["glyph"],
                color=raw["color"],
                category=raw["category"],
                description=raw["description"],
                starter=raw["starter"],
                sort_order=raw["sort_order"],
                characters=tuple(
                    SeedCharacter(
                        hanzi=character["hanzi"],
                        pinyin=character["pinyin"],
                        meaning=character["meaning"],
                    )
                    for character in raw["characters"]
                ),
                sentences=tuple(
                    SeedSentence(
                        hanzi=sentence["hanzi"],
                        pinyin=sentence["pinyin"],
                        translation=sentence["translation"],
                    )
                    for sentence in raw["sentences"]
                ),
            )
        )
    return tuple(sorted(packs, key=lambda pack: pack.sort_order))


def required_hanzi(packs: Sequence[SeedPack]) -> set[str]:
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
    chars: Iterable[str],
) -> dict[str, Character]:
    required = set(chars)
    characters = await load_characters(session, required)
    missing = required - characters.keys()
    if missing:
        raise MissingCharactersError(missing)
    return characters


async def upsert_category(session: AsyncSession, seed_category: SeedCategory) -> None:
    result = await session.execute(
        select(Category).where(Category.slug == seed_category.slug)
    )
    category = result.scalar_one_or_none()
    if category is None:
        category = Category(slug=seed_category.slug)
        session.add(category)

    category.title = seed_category.title
    category.sort_order = seed_category.sort_order


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
    pack.category_slug = seed_pack.category
    pack.description = seed_pack.description
    pack.starter = seed_pack.starter
    pack.sort_order = seed_pack.sort_order
    await session.flush()

    # Rewrite member/sentence rows only when their content actually changed.
    # This is not just an optimization: sentence review states key their
    # ``unit_ref`` on the sentence PK, and seeding runs on every bootstrap —
    # an unconditional delete/reinsert would mint new sentence ids each
    # deploy and orphan every learner's sentence review progress.
    desired_characters = [
        (
            index,
            characters[seed_character.hanzi].id,
            seed_character.pinyin,
            seed_character.meaning,
        )
        for index, seed_character in enumerate(seed_pack.characters, start=1)
    ]
    existing_characters = [
        (row.position, row.character_id, row.pinyin, row.meaning)
        for row in (
            await session.execute(
                select(PackCharacter)
                .where(PackCharacter.pack_id == pack.id)
                .order_by(PackCharacter.position)
            )
        ).scalars()
    ]
    if existing_characters != desired_characters:
        await session.execute(
            delete(PackCharacter).where(PackCharacter.pack_id == pack.id)
        )
        await session.flush()
        session.add_all(
            PackCharacter(
                pack_id=pack.id,
                character_id=character_id,
                position=position,
                pinyin=pinyin,
                meaning=meaning,
            )
            for position, character_id, pinyin, meaning in desired_characters
        )

    desired_sentences = [
        (index, seed_sentence.hanzi, seed_sentence.pinyin, seed_sentence.translation)
        for index, seed_sentence in enumerate(seed_pack.sentences, start=1)
    ]
    existing_sentences = [
        (row.position, row.hanzi, row.pinyin, row.translation)
        for row in (
            await session.execute(
                select(PackSentence)
                .where(PackSentence.pack_id == pack.id)
                .order_by(PackSentence.position)
            )
        ).scalars()
    ]
    if existing_sentences != desired_sentences:
        await session.execute(
            delete(PackSentence).where(PackSentence.pack_id == pack.id)
        )
        await session.flush()
        session.add_all(
            PackSentence(
                pack_id=pack.id,
                position=position,
                hanzi=hanzi,
                pinyin=pinyin,
                translation=translation,
            )
            for position, hanzi, pinyin, translation in desired_sentences
        )


async def seed_database(
    packs: Sequence[SeedPack] | None = None,
    categories: Sequence[SeedCategory] | None = None,
) -> SeedResult:
    """Upsert categories and curated packs (from ``data/packs`` by default).

    Idempotent by slug; never deletes packs or categories absent from the
    inputs — retiring library content users may have progress on is a
    deliberate manual operation, not a seed side effect.
    """
    if packs is None:
        packs = load_seed_packs()
    if categories is None:
        categories = load_seed_categories()

    async with db.async_session() as session:
        for seed_category in categories:
            await upsert_category(session, seed_category)
        await session.flush()

        required = required_hanzi(packs)
        characters = await validate_required_characters(session, required)
        for seed_pack in packs:
            await upsert_pack(session, seed_pack, characters)
        await session.commit()
    return SeedResult(chars=len(required), packs=len(packs), categories=len(categories))


def format_bootstrap_completed(result: SeedResult) -> str:
    return (
        f"bootstrap_completed chars={result.chars} packs={result.packs} "
        f"categories={result.categories}"
    )


def emit_bootstrap_completed(
    result: SeedResult, *, migrations_applied: bool = True
) -> None:
    """Emit the canonical bootstrap workflow event."""
    emit_workflow_event(
        "bootstrap_completed",
        workflow="WF-01",
        chars_imported=result.chars,
        packs_seeded=result.packs,
        categories_seeded=result.categories,
        migrations_applied=migrations_applied,
    )


def main() -> None:
    result = asyncio.run(seed_database())
    emit_bootstrap_completed(result)
    print(format_bootstrap_completed(result))


if __name__ == "__main__":
    main()
