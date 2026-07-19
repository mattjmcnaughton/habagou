"""Data access for character packs and their contents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import ColumnElement, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import selectinload

from habagou.models import (
    Category,
    Character,
    Pack,
    PackCharacter,
    PackSentence,
    UserPackSetting,
)

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
class LibraryPack:
    """A global pack as listed in the library, with its enablement state."""

    pack: Pack
    character_count: int
    sentence_count: int
    enabled: bool


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


_CHARACTER_COUNT = (
    select(func.count(PackCharacter.character_id))
    .where(PackCharacter.pack_id == Pack.id)
    .correlate(Pack)
    .scalar_subquery()
)
_SENTENCE_COUNT = (
    select(func.count(PackSentence.id))
    .where(PackSentence.pack_id == Pack.id)
    .correlate(Pack)
    .scalar_subquery()
)

#: Global packs should always carry a category; sort any stragglers last.
_UNCATEGORIZED_LAST = 1_000_000


def _setting_join(user_id: uuid.UUID) -> ColumnElement[bool]:
    """Join clause for the calling user's enablement overlay row (if any)."""
    return (UserPackSetting.pack_id == Pack.id) & (UserPackSetting.user_id == user_id)


def _bench_predicate(user_id: uuid.UUID) -> ColumnElement[bool]:
    """Owned, or global and effectively enabled (requires ``_setting_join``)."""
    return (Pack.owner_id == user_id) | (
        Pack.owner_id.is_(None) & func.coalesce(UserPackSetting.enabled, Pack.starter)
    )


class PackRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_visible(self, *, user_id: uuid.UUID) -> list[PackWithCounts]:
        """Packs on a user's bench: owned plus *enabled* global packs.

        Global-pack enablement is the lazy overlay from ``user_pack_settings``:
        ``COALESCE(setting.enabled, packs.starter)`` — a missing row falls back
        to the pack's starter default, so starter packs appear for every user
        without per-user rows. Disabled global packs stay reachable through
        :meth:`get_visible` (library preview) and :meth:`list_library`.
        """
        result = await self.session.execute(
            select(Pack, _CHARACTER_COUNT, _SENTENCE_COUNT)
            .outerjoin(UserPackSetting, _setting_join(user_id))
            .where(_bench_predicate(user_id))
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

    async def list_library(self, *, user_id: uuid.UUID) -> list[LibraryPack]:
        """Every global pack with counts and the user's enablement state.

        One query, no progress aggregates (the library lists hundreds of
        packs; per-pack progress stays a bench concern). Ordered by category
        sort order then pack sort order so the service can group in a single
        pass; categories come from :meth:`list_categories`.
        """
        enabled = func.coalesce(UserPackSetting.enabled, Pack.starter)
        result = await self.session.execute(
            select(Pack, _CHARACTER_COUNT, _SENTENCE_COUNT, enabled)
            .outerjoin(UserPackSetting, _setting_join(user_id))
            .outerjoin(Category, Category.slug == Pack.category_slug)
            .where(Pack.owner_id.is_(None))
            .order_by(
                func.coalesce(Category.sort_order, _UNCATEGORIZED_LAST),
                Pack.sort_order,
                Pack.id,
            )
        )
        return [
            LibraryPack(
                pack=row[0],
                character_count=row[1],
                sentence_count=row[2],
                enabled=row[3],
            )
            for row in result.all()
        ]

    async def list_global(self) -> list[Pack]:
        """All global packs, no content eager-loading (display metadata only)."""
        result = await self.session.execute(
            select(Pack)
            .where(Pack.owner_id.is_(None))
            .order_by(Pack.sort_order, Pack.id)
        )
        return list(result.scalars())

    async def list_categories(self) -> list[Category]:
        result = await self.session.execute(
            select(Category).order_by(Category.sort_order, Category.slug)
        )
        return list(result.scalars())

    async def get_setting(
        self, *, user_id: uuid.UUID, pack_id: uuid.UUID
    ) -> UserPackSetting | None:
        result = await self.session.execute(
            select(UserPackSetting).where(
                UserPackSetting.user_id == user_id,
                UserPackSetting.pack_id == pack_id,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_setting(
        self, *, user_id: uuid.UUID, pack_id: uuid.UUID, enabled: bool
    ) -> None:
        """Record an explicit enablement choice (idempotent)."""
        statement = insert(UserPackSetting).values(
            user_id=user_id, pack_id=pack_id, enabled=enabled
        )
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=[UserPackSetting.user_id, UserPackSetting.pack_id],
                set_={"enabled": statement.excluded.enabled, "updated_at": func.now()},
            )
        )

    async def list_enabled_with_content(self, *, user_id: uuid.UUID) -> list[Pack]:
        """Enabled global packs in curriculum order, with content.

        Used to build the scheduler :class:`Curriculum` for one user; the
        enablement overlay (see :meth:`list_visible`) makes the curriculum
        per-user. Characters carry their pinyin/meaning and are ordered by
        ``position``. The Learning Path is global-only, so owned packs are
        excluded even though they are always enabled.
        """
        result = await self.session.execute(
            select(Pack)
            .outerjoin(UserPackSetting, _setting_join(user_id))
            .where(
                Pack.owner_id.is_(None),
                func.coalesce(UserPackSetting.enabled, Pack.starter),
            )
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

    async def delete(self, pack_id: uuid.UUID) -> None:
        """Delete a pack row by id.

        Only the ``packs`` row is removed here; every dependent table
        (``pack_characters``, ``pack_sentences``, ``activity_completions``,
        ``path_items``, ``review_states``) carries ``ON DELETE CASCADE`` on its
        ``pack_id`` FK, so the database removes the pack's children in the same
        transaction. Callers must confirm the pack is deletable (visible and
        owned) first; this method does not re-check.
        """
        await self.session.execute(delete(Pack).where(Pack.id == pack_id))

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
