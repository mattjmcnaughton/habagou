"""Data access for the materialized, append-only Learning Path queue."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from habagou.models import (
    ActivityCompletion,
    ActivityType,
    CompletionSource,
    PathItem,
    PathItemKind,
)

if TYPE_CHECKING:
    import datetime
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


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
