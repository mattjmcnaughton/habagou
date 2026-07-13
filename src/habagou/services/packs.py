"""Pack application service."""

from __future__ import annotations

import uuid  # noqa: TC003 - used in runtime method signatures.
from typing import TYPE_CHECKING

from habagou.dtos.packs import (
    ActivityProgressDTO,
    PackCharacterDTO,
    PackDetailDTO,
    PackProgressDTO,
    PackSentenceDTO,
    PackSummaryDTO,
)
from habagou.models import ActivityType, User
from habagou.repositories import (
    ActivityProgress,
    PackRepository,
    PackWithCounts,
    ProgressRepository,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class PackService:
    def __init__(self, session: AsyncSession) -> None:
        self.pack_repository = PackRepository(session)
        self.progress_repository = ProgressRepository(session)

    async def list_visible(self, user: User) -> list[PackSummaryDTO]:
        packs = await self.pack_repository.list_visible(user_id=user.id)
        return [await self._summary(item, user) for item in packs]

    async def get_visible(self, pack_id: uuid.UUID, user: User) -> PackDetailDTO | None:
        # Visibility (global or owned) is enforced in the repository query.
        pack = await self.pack_repository.get_visible(pack_id, user.id)
        if pack is None:
            return None

        counts = PackWithCounts(
            pack=pack,
            character_count=len(pack.characters),
            sentence_count=len(pack.sentences),
        )
        summary = await self._summary(counts, user)
        return PackDetailDTO(
            **summary.model_dump(),
            characters=[
                PackCharacterDTO(
                    hanzi=link.character.hanzi,
                    pinyin=link.pinyin,
                    meaning=link.meaning,
                )
                for link in pack.characters
            ],
            sentences=[
                PackSentenceDTO(
                    hanzi=sentence.hanzi,
                    pinyin=sentence.pinyin,
                    translation=sentence.translation,
                )
                for sentence in pack.sentences
            ],
        )

    async def _summary(self, item: PackWithCounts, user: User) -> PackSummaryDTO:
        progress = await self.progress_repository.per_pack_aggregate(
            user_id=user.id,
            pack_id=item.pack.id,
        )
        return PackSummaryDTO(
            id=item.pack.id,
            title=item.pack.title,
            glyph=item.pack.glyph,
            color=item.pack.color,
            char_count=item.character_count,
            sentence_count=item.sentence_count,
            progress=pack_progress_dto(progress),
        )


def _activity_progress(progress: ActivityProgress) -> ActivityProgressDTO:
    return ActivityProgressDTO(
        completed=progress.completed,
        completion_count=progress.completion_count,
        best_duration_ms=progress.best_duration_ms,
    )


def pack_progress_dto(
    progress: dict[ActivityType, ActivityProgress],
) -> PackProgressDTO:
    return PackProgressDTO(
        trace=_activity_progress(progress[ActivityType.TRACE]),
        match=_activity_progress(progress[ActivityType.MATCH]),
        sentence=_activity_progress(progress[ActivityType.SENTENCE]),
    )
