"""Data access for the rebuildable spaced-repetition projection."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from habagou.models import ActivityType, ReviewState, ReviewUnitType

if TYPE_CHECKING:
    import datetime
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


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
