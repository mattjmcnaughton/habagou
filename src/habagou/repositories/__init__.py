"""Database repositories for Habagou domain models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload

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
from habagou.seed_data import GUEST_USER_ID

if TYPE_CHECKING:
    import datetime
    import uuid
    from collections.abc import Iterable

    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class PackWithCounts:
    pack: Pack
    character_count: int
    sentence_count: int


@dataclass(frozen=True)
class ActivityProgress:
    activity: ActivityType
    completed: bool
    completion_count: int
    best_duration_ms: int | None


class PackRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_published(self) -> list[PackWithCounts]:
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
            .where(Pack.status == PackStatus.PUBLISHED)
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

    async def get_by_slug(self, slug: str) -> Pack | None:
        result = await self.session.execute(
            select(Pack)
            .where(Pack.slug == slug)
            .options(
                selectinload(Pack.characters).selectinload(PackCharacter.character),
                selectinload(Pack.sentences),
            )
        )
        return result.scalar_one_or_none()

    async def set_status(self, slug: str, status: PackStatus) -> Pack | None:
        pack = await self.get_by_slug(slug)
        if pack is None:
            return None
        pack.status = status
        await self.session.flush()
        return pack

    async def set_sort_order(self, slug: str, sort_order: int) -> Pack | None:
        pack = await self.get_by_slug(slug)
        if pack is None:
            return None
        pack.sort_order = sort_order
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


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_guest(self) -> User | None:
        result = await self.session.execute(
            select(User).where(User.id == GUEST_USER_ID, User.username == "guest")
        )
        return result.scalar_one_or_none()


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
    ) -> ActivityCompletion:
        completion = ActivityCompletion(
            user_id=user_id,
            pack_id=pack_id,
            activity=activity,
            duration_ms=duration_ms,
        )
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


__all__ = [
    "ActivityProgress",
    "CharacterRepository",
    "PackRepository",
    "PackWithCounts",
    "ProgressRepository",
    "UserRepository",
]
