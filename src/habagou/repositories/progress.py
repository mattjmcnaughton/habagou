"""Data access for the append-only activity completion log."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import delete, func, select

from habagou.models import ActivityCompletion, ActivityType, CompletionSource

if TYPE_CHECKING:
    import datetime
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class ActivityProgress:
    activity: ActivityType
    completed: bool
    completion_count: int
    best_duration_ms: int | None


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
