"""Data access for the Hanzi stroke corpus."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from habagou.models import Character

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy.ext.asyncio import AsyncSession


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
