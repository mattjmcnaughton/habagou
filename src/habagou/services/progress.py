"""Progress application service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from habagou.dtos.packs import ActivityProgressDTO, PackProgressDTO
from habagou.dtos.progress import (
    CompletionCreateDTO,
    CompletionResponseDTO,
    PackProgressResponseDTO,
    ProgressResetDTO,
)
from habagou.models import ActivityType, Pack, PackStatus, User
from habagou.repositories import ActivityProgress, PackRepository, ProgressRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class ProgressService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.pack_repository = PackRepository(session)
        self.progress_repository = ProgressRepository(session)

    async def record_completion(
        self,
        *,
        user: User,
        completion: CompletionCreateDTO,
    ) -> CompletionResponseDTO | None:
        pack = await self._published_pack(completion.pack_slug)
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
        pack_slug: str,
    ) -> PackProgressResponseDTO | None:
        pack = await self._published_pack(pack_slug)
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
        pack_slug: str,
    ) -> ProgressResetDTO | None:
        pack = await self._published_pack(pack_slug)
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

    async def _published_pack(self, slug: str) -> Pack | None:
        pack = await self.pack_repository.get_by_slug(slug)
        if pack is None or pack.status is not PackStatus.PUBLISHED:
            return None
        return pack

    async def _progress(self, *, user: User, pack: Pack) -> PackProgressDTO:
        progress = await self.progress_repository.per_pack_aggregate(
            user_id=user.id,
            pack_id=pack.id,
        )
        return PackProgressDTO(
            trace=_activity_progress(progress[ActivityType.TRACE]),
            match=_activity_progress(progress[ActivityType.MATCH]),
            sentence=_activity_progress(progress[ActivityType.SENTENCE]),
        )


def _activity_progress(progress: ActivityProgress) -> ActivityProgressDTO:
    return ActivityProgressDTO(
        completed=progress.completed,
        completion_count=progress.completion_count,
        best_duration_ms=progress.best_duration_ms,
    )
