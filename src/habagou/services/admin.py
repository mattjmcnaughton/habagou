"""Admin application service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from habagou.dtos.admin import PackAdminDTO
from habagou.models import Pack, PackStatus
from habagou.repositories import PackRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class AdminService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.pack_repository = PackRepository(session)

    async def publish_pack(self, slug: str) -> PackAdminDTO | None:
        return await self._set_status(slug, PackStatus.PUBLISHED)

    async def retire_pack(self, slug: str) -> PackAdminDTO | None:
        return await self._set_status(slug, PackStatus.RETIRED)

    async def set_pack_sort_order(
        self, slug: str, sort_order: int
    ) -> PackAdminDTO | None:
        pack = await self.pack_repository.set_sort_order(slug, sort_order)
        if pack is None:
            return None
        await self.session.commit()
        return _pack_admin(pack)

    async def _set_status(self, slug: str, status: PackStatus) -> PackAdminDTO | None:
        pack = await self.pack_repository.set_status(slug, status)
        if pack is None:
            return None
        await self.session.commit()
        return _pack_admin(pack)


def _pack_admin(pack: Pack) -> PackAdminDTO:
    return PackAdminDTO(
        id=pack.id,
        slug=pack.slug,
        title=pack.title,
        status=pack.status,
        sort_order=pack.sort_order,
    )
