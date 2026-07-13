"""Database repositories for Habagou domain models."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload

from habagou.models import (
    ActivityCompletion,
    ActivityType,
    Character,
    CompletionSource,
    Pack,
    PackCharacter,
    PackSentence,
    PathItem,
    PathItemKind,
    ReviewState,
    ReviewUnitType,
    User,
)

if TYPE_CHECKING:
    import datetime
    from collections.abc import Iterable, Sequence

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


@dataclass(frozen=True)
class ActivityProgress:
    activity: ActivityType
    completed: bool
    completion_count: int
    best_duration_ms: int | None


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def lock_by_id(self, user_id: uuid.UUID) -> User | None:
        """Lock a user's row until the current transaction finishes."""
        result = await self.session.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_by_identity(self, issuer: str, subject: str) -> User | None:
        result = await self.session.execute(
            select(User).where(
                User.auth_issuer == issuer,
                User.auth_subject == subject,
            )
        )
        return result.scalar_one_or_none()

    async def username_exists(self, username: str) -> bool:
        result = await self.session.execute(
            select(User.id).where(User.username == username)
        )
        return result.scalar_one_or_none() is not None

    async def create(
        self,
        *,
        username: str,
        display_name: str,
        auth_issuer: str,
        auth_subject: str,
        email: str | None,
    ) -> User:
        user = User(
            username=username,
            display_name=display_name,
            is_guest=False,
            auth_issuer=auth_issuer,
            auth_subject=auth_subject,
            email=email,
        )
        self.session.add(user)
        await self.session.flush()
        return user


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
            .order_by(Pack.sort_order, Pack.slug)
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
            .order_by(Pack.sort_order, Pack.slug)
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
        non-null ``owner_id`` a private one. Character members are referenced by
        ``hanzi`` against the existing corpus (a ``ValueError`` is raised for any
        hanzi missing from it); ``position`` is assigned from list order
        (1-based), matching the seed convention. ``slug`` is generated when
        omitted -- user packs have no slug, but the column stays NOT NULL until
        HAB-070. Epic 7 wires the pack-Save endpoint to this method.
        """
        wanted_hanzi = [character.hanzi for character in characters]
        result = await self.session.execute(
            select(Character).where(Character.hanzi.in_(wanted_hanzi))
        )
        by_hanzi = {character.hanzi: character for character in result.scalars()}
        missing = [hanzi for hanzi in wanted_hanzi if hanzi not in by_hanzi]
        if missing:
            raise ValueError(
                f"pack references characters missing from corpus: {''.join(missing)}"
            )

        pack = Pack(
            owner_id=owner_id,
            slug=slug if slug is not None else f"pack-{uuid.uuid4().hex}",
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


class CharacterRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def strokes_by_hanzi(self, hanzi: str) -> dict[str, Any] | None:
        result = await self.session.execute(
            select(Character.stroke_data).where(Character.hanzi == hanzi)
        )
        return result.scalar_one_or_none()

    async def missing_hanzi(self, hanzi: Iterable[str]) -> set[str]:
        required = set(hanzi)
        if not required:
            return set()
        result = await self.session.execute(
            select(Character.hanzi).where(Character.hanzi.in_(required))
        )
        existing = set(result.scalars())
        return required - existing


class ProgressRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(
        self,
        *,
        user_id: uuid.UUID,
        pack_id: uuid.UUID,
        activity: ActivityType,
        duration_ms: int,
        source: CompletionSource = CompletionSource.PACK,
        path_item_id: uuid.UUID | None = None,
        completed_at: datetime.datetime | None = None,
    ) -> ActivityCompletion:
        completion = ActivityCompletion(
            user_id=user_id,
            pack_id=pack_id,
            activity=activity,
            duration_ms=duration_ms,
            source=source,
            path_item_id=path_item_id,
        )
        if completed_at is not None:
            completion.completed_at = completed_at
        self.session.add(completion)
        await self.session.flush()
        return completion

    async def per_pack_aggregate(
        self,
        *,
        user_id: uuid.UUID,
        pack_id: uuid.UUID,
    ) -> dict[ActivityType, ActivityProgress]:
        result = await self.session.execute(
            select(
                ActivityCompletion.activity,
                func.count(ActivityCompletion.id),
                func.min(ActivityCompletion.duration_ms),
            )
            .where(
                ActivityCompletion.user_id == user_id,
                ActivityCompletion.pack_id == pack_id,
                ActivityCompletion.source == CompletionSource.PACK,
            )
            .group_by(ActivityCompletion.activity)
        )
        rows = {row[0]: (row[1], row[2]) for row in result.all()}
        return {
            activity: ActivityProgress(
                activity=activity,
                completed=activity in rows,
                completion_count=rows.get(activity, (0, None))[0],
                best_duration_ms=rows.get(activity, (0, None))[1],
            )
            for activity in ActivityType
        }

    async def daily_completion_counts(
        self,
        *,
        user_id: uuid.UUID,
        tz_offset_minutes: int = 0,
    ) -> dict[datetime.date, int]:
        local_day = func.date(
            ActivityCompletion.completed_at
            - func.make_interval(0, 0, 0, 0, 0, tz_offset_minutes)
        )
        result = await self.session.execute(
            select(local_day, func.count(ActivityCompletion.id))
            .where(ActivityCompletion.user_id == user_id)
            .group_by(local_day)
            .order_by(local_day)
        )
        return {row[0]: row[1] for row in result.all()}

    async def delete_by_user_pack(
        self,
        *,
        user_id: uuid.UUID,
        pack_id: uuid.UUID,
    ) -> int:
        result = await self.session.execute(
            delete(ActivityCompletion).where(
                ActivityCompletion.user_id == user_id,
                ActivityCompletion.pack_id == pack_id,
            )
        )
        rowcount = getattr(result, "rowcount", 0)
        return int(rowcount or 0)


class PathRepository:
    """Data access for the materialized, append-only path item queue.

    Path items are created here and never mutated or deleted; display state is
    derived at read time from the completion event log.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def append(
        self,
        *,
        user_id: uuid.UUID,
        position: int,
        activity: ActivityType,
        kind: PathItemKind,
        pack_id: uuid.UUID,
        content: dict[str, Any],
    ) -> PathItem:
        item = PathItem(
            user_id=user_id,
            position=position,
            activity=activity,
            kind=kind,
            pack_id=pack_id,
            content=content,
        )
        self.session.add(item)
        await self.session.flush()
        return item

    async def get_by_id(self, item_id: uuid.UUID) -> PathItem | None:
        result = await self.session.execute(
            select(PathItem).where(PathItem.id == item_id)
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self,
        *,
        user_id: uuid.UUID,
        after_position: int | None = None,
        limit: int | None = None,
    ) -> list[PathItem]:
        query = (
            select(PathItem)
            .where(PathItem.user_id == user_id)
            .order_by(PathItem.position)
        )
        if after_position is not None:
            query = query.where(PathItem.position > after_position)
        if limit is not None:
            query = query.limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars())

    async def has_completion(self, item_id: uuid.UUID) -> bool:
        """Whether the given path item already has a recorded path completion."""
        result = await self.session.execute(
            select(ActivityCompletion.id)
            .where(
                ActivityCompletion.source == CompletionSource.PATH,
                ActivityCompletion.path_item_id == item_id,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def first_pending(self, *, user_id: uuid.UUID) -> PathItem | None:
        """The lowest-position not-yet-completed item (the new 'current')."""
        completed = select(ActivityCompletion.path_item_id).where(
            ActivityCompletion.user_id == user_id,
            ActivityCompletion.source == CompletionSource.PATH,
            ActivityCompletion.path_item_id.is_not(None),
        )
        result = await self.session.execute(
            select(PathItem)
            .where(
                PathItem.user_id == user_id,
                PathItem.id.not_in(completed),
            )
            .order_by(PathItem.position)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def max_position(self, *, user_id: uuid.UUID) -> int | None:
        result = await self.session.execute(
            select(func.max(PathItem.position)).where(PathItem.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def count_pending(self, *, user_id: uuid.UUID) -> int:
        completed = select(ActivityCompletion.path_item_id).where(
            ActivityCompletion.user_id == user_id,
            ActivityCompletion.source == CompletionSource.PATH,
            ActivityCompletion.path_item_id.is_not(None),
        )
        result = await self.session.execute(
            select(func.count(PathItem.id)).where(
                PathItem.user_id == user_id,
                PathItem.id.not_in(completed),
            )
        )
        return int(result.scalar_one())

    async def completions_by_item(
        self, *, user_id: uuid.UUID
    ) -> dict[uuid.UUID, datetime.datetime]:
        """Map each completed path item to its completion timestamp.

        An item has at most one path completion (enforced at the service layer),
        so this is the source of the derived done/current/locked display state.
        """
        result = await self.session.execute(
            select(
                ActivityCompletion.path_item_id,
                ActivityCompletion.completed_at,
            ).where(
                ActivityCompletion.user_id == user_id,
                ActivityCompletion.source == CompletionSource.PATH,
                ActivityCompletion.path_item_id.is_not(None),
            )
        )
        return {row[0]: row[1] for row in result.all()}

    async def completed_trace_items(self, *, user_id: uuid.UUID) -> list[PathItem]:
        """Trace-activity path items that have a recorded path completion.

        Used to derive ``characters_traced`` for the progress summary: the
        ``content`` snapshot on each returned item carries the traced hanzi.
        """
        completed = select(ActivityCompletion.path_item_id).where(
            ActivityCompletion.user_id == user_id,
            ActivityCompletion.source == CompletionSource.PATH,
            ActivityCompletion.path_item_id.is_not(None),
        )
        result = await self.session.execute(
            select(PathItem).where(
                PathItem.user_id == user_id,
                PathItem.activity == ActivityType.TRACE,
                PathItem.id.in_(completed),
            )
        )
        return list(result.scalars())

    async def path_completions_ordered(
        self, *, user_id: uuid.UUID
    ) -> list[tuple[uuid.UUID, datetime.datetime]]:
        """Path completion events oldest first (for projection replay)."""
        result = await self.session.execute(
            select(
                ActivityCompletion.path_item_id,
                ActivityCompletion.completed_at,
            )
            .where(
                ActivityCompletion.user_id == user_id,
                ActivityCompletion.source == CompletionSource.PATH,
                ActivityCompletion.path_item_id.is_not(None),
            )
            .order_by(ActivityCompletion.completed_at, ActivityCompletion.id)
        )
        return [(row[0], row[1]) for row in result.all()]


class ReviewStateRepository:
    """Data access for the rebuildable spaced-repetition projection.

    Every write here is derivable by replaying the append-only completion event
    log (see ADR-0008).
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(
        self,
        *,
        user_id: uuid.UUID,
        pack_id: uuid.UUID,
        unit_type: ReviewUnitType,
        unit_ref: str,
        activity: ActivityType,
    ) -> ReviewState | None:
        return await self.session.get(
            ReviewState,
            (user_id, pack_id, unit_type, unit_ref, activity),
        )

    async def list_for_user(self, *, user_id: uuid.UUID) -> list[ReviewState]:
        result = await self.session.execute(
            select(ReviewState)
            .where(ReviewState.user_id == user_id)
            .order_by(ReviewState.due_at)
        )
        return list(result.scalars())

    async def upsert(
        self,
        *,
        user_id: uuid.UUID,
        pack_id: uuid.UUID,
        unit_type: ReviewUnitType,
        unit_ref: str,
        activity: ActivityType,
        reps: int,
        last_seen_at: datetime.datetime | None,
        due_at: datetime.datetime | None,
    ) -> ReviewState:
        existing = await self.get(
            user_id=user_id,
            pack_id=pack_id,
            unit_type=unit_type,
            unit_ref=unit_ref,
            activity=activity,
        )
        if existing is None:
            existing = ReviewState(
                user_id=user_id,
                pack_id=pack_id,
                unit_type=unit_type,
                unit_ref=unit_ref,
                activity=activity,
                reps=reps,
                last_seen_at=last_seen_at,
                due_at=due_at,
            )
            self.session.add(existing)
        else:
            existing.reps = reps
            existing.last_seen_at = last_seen_at
            existing.due_at = due_at
        await self.session.flush()
        return existing


__all__ = [
    "ActivityProgress",
    "CharacterRepository",
    "PackCharacterInput",
    "PackRepository",
    "PackSentenceInput",
    "PackWithCounts",
    "PathRepository",
    "ProgressRepository",
    "ReviewStateRepository",
    "UserRepository",
]
