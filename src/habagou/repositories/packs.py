"""Data access for character packs and their contents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from habagou.models import Character, Pack, PackCharacter, PackSentence

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class PackWithCounts:
    pack: Pack
    character_count: int
    sentence_count: int


@dataclass(frozen=True)
class PackCharacterInput:
    """A pack member: an existing corpus character plus its pack-local gloss."""

    hanzi: str
    pinyin: str
    meaning: str


@dataclass(frozen=True)
class PackSentenceInput:
    """A pack sentence for the sentence-tracing activity."""

    hanzi: str
    pinyin: str
    translation: str


class PackRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_visible(self, *, user_id: uuid.UUID) -> list[PackWithCounts]:
        """Packs visible to a user: global (``owner_id IS NULL``) plus own."""
        character_count = (
            select(func.count(PackCharacter.character_id))
            .where(PackCharacter.pack_id == Pack.id)
            .correlate(Pack)
            .scalar_subquery()
        )
        sentence_count = (
            select(func.count(PackSentence.id))
            .where(PackSentence.pack_id == Pack.id)
            .correlate(Pack)
            .scalar_subquery()
        )
        result = await self.session.execute(
            select(Pack, character_count, sentence_count)
            .where((Pack.owner_id.is_(None)) | (Pack.owner_id == user_id))
            .order_by(Pack.sort_order, Pack.id)
        )
        return [
            PackWithCounts(
                pack=row[0],
                character_count=row[1],
                sentence_count=row[2],
            )
            for row in result.all()
        ]

    async def list_global_with_content(self) -> list[Pack]:
        """Global packs (``owner_id IS NULL``) in curriculum order, with content.

        Used to build the scheduler :class:`Curriculum`; characters carry their
        pinyin/meaning and are ordered by ``position``. The Learning Path is
        global-only this epic, so owned packs are excluded.
        """
        result = await self.session.execute(
            select(Pack)
            .where(Pack.owner_id.is_(None))
            .order_by(Pack.sort_order, Pack.id)
            .options(
                selectinload(Pack.characters).selectinload(PackCharacter.character),
                selectinload(Pack.sentences),
            )
        )
        return list(result.scalars())

    async def get_by_id(self, pack_id: uuid.UUID) -> Pack | None:
        result = await self.session.execute(
            select(Pack)
            .where(Pack.id == pack_id)
            .options(
                selectinload(Pack.characters).selectinload(PackCharacter.character),
                selectinload(Pack.sentences),
            )
        )
        return result.scalar_one_or_none()

    async def get_visible(self, pack_id: uuid.UUID, user_id: uuid.UUID) -> Pack | None:
        """Fetch a pack by id iff it is visible to ``user_id``.

        Visible means global (``owner_id IS NULL``) or owned by the caller; the
        ownership predicate is pushed into SQL (mirroring :meth:`list_visible`)
        so callers never re-check visibility in Python.
        """
        result = await self.session.execute(
            select(Pack)
            .where(
                Pack.id == pack_id,
                (Pack.owner_id.is_(None)) | (Pack.owner_id == user_id),
            )
            .options(
                selectinload(Pack.characters).selectinload(PackCharacter.character),
                selectinload(Pack.sentences),
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        owner_id: uuid.UUID | None,
        title: str,
        glyph: str,
        color: str,
        sort_order: int,
        characters: Sequence[PackCharacterInput],
        sentences: Sequence[PackSentenceInput],
        slug: str | None = None,
    ) -> Pack:
        """Persist a pack with its character and sentence rows.

        Mirrors the seed write path (:func:`scripts.seed.upsert_pack`) but for a
        single pack: ``owner_id=None`` creates a global (curated) pack and a
        non-null ``owner_id`` a private one. Every glyph the pack would trace —
        its character members *and* each glyph within every sentence (sentences
        are traced glyph by glyph) — is validated against the existing corpus (a
        ``ValueError`` is raised for any hanzi missing from it), mirroring
        :func:`scripts.seed.required_hanzi` and the agent output validator so
        this save path (grounding layer 3) cannot admit non-corpus glyphs.
        ``position`` is assigned from list order (1-based), matching the seed
        convention. ``slug`` is a nullable seed key: it persists as NULL when
        omitted (user packs have no slug), while the seed upsert supplies stable
        non-null slugs. Epic 7 wires the pack-Save endpoint to this method.
        """
        member_hanzi = [character.hanzi for character in characters]
        sentence_glyphs = [
            glyph for sentence in sentences for glyph in sentence.hanzi if glyph.strip()
        ]
        # Dedup, first-seen order preserved: pack members are looked up for their
        # character FK; sentence glyphs need corpus membership only.
        required = list(dict.fromkeys(member_hanzi + sentence_glyphs))
        result = await self.session.execute(
            select(Character).where(Character.hanzi.in_(required))
        )
        by_hanzi = {character.hanzi: character for character in result.scalars()}
        missing = [hanzi for hanzi in required if hanzi not in by_hanzi]
        if missing:
            raise ValueError(
                f"pack references characters missing from corpus: {''.join(missing)}"
            )

        pack = Pack(
            owner_id=owner_id,
            slug=slug,
            title=title,
            glyph=glyph,
            color=color,
            sort_order=sort_order,
        )
        self.session.add(pack)
        await self.session.flush()

        self.session.add_all(
            PackCharacter(
                pack_id=pack.id,
                character_id=by_hanzi[character.hanzi].id,
                position=index,
                pinyin=character.pinyin,
                meaning=character.meaning,
            )
            for index, character in enumerate(characters, start=1)
        )
        self.session.add_all(
            PackSentence(
                pack_id=pack.id,
                position=index,
                hanzi=sentence.hanzi,
                pinyin=sentence.pinyin,
                translation=sentence.translation,
            )
            for index, sentence in enumerate(sentences, start=1)
        )
        await self.session.flush()
        return pack
