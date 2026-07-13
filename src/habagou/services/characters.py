"""Character application service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from habagou.repositories import CharacterRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class CharacterService:
    def __init__(self, session: AsyncSession) -> None:
        self.characters = CharacterRepository(session)

    async def get_strokes(self, hanzi: str) -> dict[str, Any] | None:
        """Return the Hanzi Writer stroke JSON for a character, or ``None``.

        The caller has already validated that ``hanzi`` is a single grapheme;
        a ``None`` result means the character is absent from the corpus.
        """
        return await self.characters.strokes_by_hanzi(hanzi)
