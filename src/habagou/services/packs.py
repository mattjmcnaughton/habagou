"""Pack application service."""

from __future__ import annotations

import uuid  # noqa: TC003 - used in runtime method signatures.
from enum import Enum
from typing import TYPE_CHECKING

from habagou.dtos.packs import (
    ActivityProgressDTO,
    LibraryCategoryDTO,
    LibraryDTO,
    LibraryPackDTO,
    PackCharacterDTO,
    PackDetailDTO,
    PackProgressDTO,
    PackSentenceDTO,
    PackSummaryDTO,
)
from habagou.models import ActivityType, Pack, User
from habagou.repositories import (
    ActivityProgress,
    PackRepository,
    PackWithCounts,
    PathRepository,
    ProgressRepository,
    UserRepository,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class PackDeletion(Enum):
    """Outcome of an attempt to delete a pack on a user's behalf."""

    NOT_FOUND = "not_found"
    FORBIDDEN = "forbidden"
    DELETED = "deleted"


class PackEnablement(Enum):
    """Outcome of an attempt to change a pack's enablement for a user."""

    NOT_FOUND = "not_found"
    OWNED = "owned"
    UPDATED = "updated"


class PackService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.pack_repository = PackRepository(session)
        self.progress_repository = ProgressRepository(session)
        self.path_repository = PathRepository(session)
        self.user_repository = UserRepository(session)

    async def list_visible(self, user: User) -> list[PackSummaryDTO]:
        packs = await self.pack_repository.list_visible(user_id=user.id)
        # One grouped progress query for the whole bench instead of a query
        # per pack (a user may enable most of the 54-pack library).
        aggregates = await self.progress_repository.per_pack_aggregates(
            user_id=user.id,
            pack_ids=[item.pack.id for item in packs],
        )
        return [
            await self._summary(item, user, progress=aggregates[item.pack.id])
            for item in packs
        ]

    async def list_library(self, user: User) -> LibraryDTO:
        """The full curated library, grouped by category, with enablement."""
        categories = await self.pack_repository.list_categories()
        rows = await self.pack_repository.list_library(user_id=user.id)

        packs_by_category: dict[str | None, list[LibraryPackDTO]] = {}
        for row in rows:
            packs_by_category.setdefault(row.pack.category_slug, []).append(
                LibraryPackDTO(
                    id=row.pack.id,
                    title=row.pack.title,
                    glyph=row.pack.glyph,
                    color=row.pack.color,
                    description=row.pack.description,
                    char_count=row.character_count,
                    sentence_count=row.sentence_count,
                    starter=row.pack.starter,
                    enabled=row.enabled,
                )
            )
        category_dtos = [
            LibraryCategoryDTO(
                slug=category.slug,
                title=category.title,
                packs=packs_by_category[category.slug],
            )
            for category in categories
            if category.slug in packs_by_category
        ]
        # No write path creates a category-less global pack today, but if one
        # ever appears it must stay visible (and enable-able) rather than be
        # silently dropped; the repository already orders these last.
        orphans = packs_by_category.get(None)
        if orphans:
            category_dtos.append(
                LibraryCategoryDTO(slug="uncategorized", title="More", packs=orphans)
            )
        return LibraryDTO(categories=category_dtos)

    async def set_enabled(
        self, pack_id: uuid.UUID, user: User, *, enabled: bool
    ) -> PackEnablement:
        """Record the user's enablement choice for a global pack.

        Owned packs are always enabled — toggling them is rejected. Disabling
        prunes the user's never-completed path items for the pack in the same
        transaction (completed items, review states, and completions are kept,
        so re-enabling resumes progress).
        """
        pack = await self.pack_repository.get_visible(pack_id, user.id)
        if pack is None:
            return PackEnablement.NOT_FOUND
        if pack.owner_id is not None:
            return PackEnablement.OWNED

        # Serialize with PathService._extend_queue and complete_item (same
        # per-user lock): without it, a concurrent path read could snapshot
        # the curriculum before this disable commits and append fresh items
        # for the pack after the prune below has already run.
        await self.user_repository.lock_by_id(user.id)
        await self.pack_repository.upsert_setting(
            user_id=user.id, pack_id=pack.id, enabled=enabled
        )
        if not enabled:
            await self.path_repository.delete_pending_for_pack(
                user_id=user.id, pack_id=pack.id
            )
        await self.session.commit()
        return PackEnablement.UPDATED

    async def get_visible(self, pack_id: uuid.UUID, user: User) -> PackDetailDTO | None:
        # Visibility (global or owned) is enforced in the repository query.
        # Disabled global packs stay viewable — the library links here as a
        # preview before enabling.
        pack = await self.pack_repository.get_visible(pack_id, user.id)
        if pack is None:
            return None

        counts = PackWithCounts(
            pack=pack,
            character_count=len(pack.characters),
            sentence_count=len(pack.sentences),
        )
        summary = await self._summary(
            counts, user, enabled=await self._effective_enabled(pack, user)
        )
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

    async def delete(self, pack_id: uuid.UUID, user: User) -> PackDeletion:
        """Delete a pack on ``user``'s behalf.

        Not visible (nonexistent or owned by someone else) is indistinguishable
        from missing, so both return :attr:`PackDeletion.NOT_FOUND`. A visible
        but unowned pack is a global, curated pack — deletable only by the seed
        pipeline, never a learner — so it returns :attr:`PackDeletion.FORBIDDEN`.
        An owned pack is removed (the database cascades its children) and yields
        :attr:`PackDeletion.DELETED`.
        """
        # Visibility (global or owned) is enforced in the repository query, so
        # ownership is the only distinction left to draw in Python.
        pack = await self.pack_repository.get_visible(pack_id, user.id)
        if pack is None:
            return PackDeletion.NOT_FOUND
        if pack.owner_id != user.id:
            return PackDeletion.FORBIDDEN

        await self.pack_repository.delete(pack.id)
        await self.session.commit()
        return PackDeletion.DELETED

    async def _effective_enabled(self, pack: Pack, user: User) -> bool:
        """Owned packs are always enabled; global packs use the lazy overlay."""
        if pack.owner_id == user.id:
            return True
        setting = await self.pack_repository.get_setting(
            user_id=user.id, pack_id=pack.id
        )
        return pack.starter if setting is None else setting.enabled

    async def _summary(
        self,
        item: PackWithCounts,
        user: User,
        *,
        enabled: bool = True,
        progress: dict[ActivityType, ActivityProgress] | None = None,
    ) -> PackSummaryDTO:
        if progress is None:
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
            owned=item.pack.owner_id == user.id,
            starter=item.pack.starter,
            # The bench only lists enabled packs, so the default holds there;
            # the detail view passes the user's real overlay value.
            enabled=enabled,
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
