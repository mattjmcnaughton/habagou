"""Progress application service."""

from __future__ import annotations

import uuid  # noqa: TC003 - used in runtime method signatures.
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from habagou.dtos.progress import (
    CompletionCreateDTO,
    CompletionResponseDTO,
    DailyActivityDTO,
    DailyGoalDTO,
    NextMilestoneDTO,
    PackProgressResponseDTO,
    ProgressResetDTO,
    ProgressSummaryDTO,
)
from habagou.models import ActivityType, Pack, User
from habagou.repositories import PackRepository, PathRepository, ProgressRepository
from habagou.services.packs import pack_progress_dto
from habagou.streaks import (
    DAILY_GOAL_TARGET,
    bucket_level,
    compute_streaks,
    next_milestone,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from habagou.dtos.packs import PackProgressDTO


class ProgressService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.pack_repository = PackRepository(session)
        self.progress_repository = ProgressRepository(session)
        self.path_repository = PathRepository(session)

    async def record_completion(
        self,
        *,
        user: User,
        completion: CompletionCreateDTO,
    ) -> CompletionResponseDTO | None:
        pack = await self._visible_pack(completion.pack_id, user)
        if pack is None:
            return None

        await self.progress_repository.record(
            user_id=user.id,
            pack_id=pack.id,
            activity=completion.activity,
            duration_ms=completion.duration_ms,
        )
        await self.session.commit()
        progress = await self._progress(user=user, pack=pack)
        return CompletionResponseDTO(
            pack_slug=pack.slug,
            activity=completion.activity,
            duration_ms=completion.duration_ms,
            progress=progress,
        )

    async def get_pack_progress(
        self,
        *,
        user: User,
        pack_id: uuid.UUID,
    ) -> PackProgressResponseDTO | None:
        pack = await self._visible_pack(pack_id, user)
        if pack is None:
            return None

        return PackProgressResponseDTO(
            pack_slug=pack.slug,
            progress=await self._progress(user=user, pack=pack),
        )

    async def reset_pack_progress(
        self,
        *,
        user: User,
        pack_id: uuid.UUID,
    ) -> ProgressResetDTO | None:
        pack = await self._visible_pack(pack_id, user)
        if pack is None:
            return None

        deleted_count = await self.progress_repository.delete_by_user_pack(
            user_id=user.id,
            pack_id=pack.id,
        )
        await self.session.commit()
        return ProgressResetDTO(
            pack_slug=pack.slug,
            deleted_count=deleted_count,
            progress=await self._progress(user=user, pack=pack),
        )

    async def get_summary(
        self,
        *,
        user: User,
        tz_offset_minutes: int = 0,
    ) -> ProgressSummaryDTO:
        daily_counts = await self.progress_repository.daily_completion_counts(
            user_id=user.id,
            tz_offset_minutes=tz_offset_minutes,
        )
        today = (datetime.now(UTC) - timedelta(minutes=tz_offset_minutes)).date()
        streaks = compute_streaks(daily_counts, today=today)
        milestone = next_milestone(streaks.current)
        activity = [
            DailyActivityDTO(
                date=day,
                count=(count := daily_counts.get(day, 0)),
                level=bucket_level(count),
            )
            for day in (today - timedelta(days=offset) for offset in range(44, -1, -1))
        ]

        characters_traced, packs_completed, packs_total = await self._path_stats(
            user=user
        )

        return ProgressSummaryDTO(
            current_streak=streaks.current,
            best_streak=streaks.best,
            daily_goal=DailyGoalDTO(
                completed=daily_counts.get(today, 0),
                target=DAILY_GOAL_TARGET,
            ),
            activity=activity,
            next_milestone=NextMilestoneDTO(
                target_days=milestone.target_days,
                days_remaining=milestone.days_remaining,
                progress_pct=milestone.progress_pct,
            ),
            characters_traced=characters_traced,
            packs_completed=packs_completed,
            packs_total=packs_total,
        )

    async def _path_stats(self, *, user: User) -> tuple[int, int, int]:
        """Return ``(characters_traced, packs_completed, packs_total)``.

        ``characters_traced`` unions two sources of traced hanzi: characters
        drawn in completed path-item Trace lessons (from the pinned
        ``content`` snapshot), and every character of packs whose whole-pack
        Trace activity is complete. ``packs_completed`` reuses the same
        per-pack aggregate (``source='pack'``) that drives the pack progress
        badges: all three activities must be complete.
        """
        packs = await self.pack_repository.list_global_with_content()
        traced_hanzi: set[str] = set()
        packs_completed = 0
        for pack in packs:
            aggregate = await self.progress_repository.per_pack_aggregate(
                user_id=user.id,
                pack_id=pack.id,
            )
            if aggregate[ActivityType.TRACE].completed:
                traced_hanzi.update(link.character.hanzi for link in pack.characters)
            if all(aggregate[activity].completed for activity in ActivityType):
                packs_completed += 1

        trace_items = await self.path_repository.completed_trace_items(user_id=user.id)
        for item in trace_items:
            chars = item.content.get("activity_content", {}).get("chars", [])
            traced_hanzi.update(
                char["hanzi"]
                for char in chars
                if isinstance(char, dict) and "hanzi" in char
            )

        return len(traced_hanzi), packs_completed, len(packs)

    async def _visible_pack(self, pack_id: uuid.UUID, user: User) -> Pack | None:
        # Visibility (global or owned) is enforced in the repository query.
        return await self.pack_repository.get_visible(pack_id, user.id)

    async def _progress(self, *, user: User, pack: Pack) -> PackProgressDTO:
        progress = await self.progress_repository.per_pack_aggregate(
            user_id=user.id,
            pack_id=pack.id,
        )
        return pack_progress_dto(progress)
