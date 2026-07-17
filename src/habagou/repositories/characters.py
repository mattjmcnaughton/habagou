"""Data access for the Hanzi stroke corpus."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from habagou.models import Character

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy.ext.asyncio import AsyncSession


# The full corpus is static (loaded once at deploy time by
# ``scripts.import_stroke_data``), so ``all_hanzi`` caches its result
# process-wide rather than re-querying on every pack generation. Held at module
# scope so the cache is shared across repository instances and independent of any
# one session. ``reset_all_hanzi_cache`` clears it for tests.
_all_hanzi_cache: tuple[str, ...] | None = None


def reset_all_hanzi_cache() -> None:
    """Clear the process-wide corpus-membership cache (test hook)."""
    global _all_hanzi_cache
    _all_hanzi_cache = None


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

    async def stroke_counts(self, hanzi: Iterable[str]) -> dict[str, int]:
        """Stroke count for each requested hanzi that exists in the corpus.

        One query. Missing hanzi are simply absent from the returned mapping, so
        callers can use it both as a difficulty signal and as a membership
        witness for the found set.
        """
        wanted = set(hanzi)
        if not wanted:
            return {}
        result = await self.session.execute(
            select(Character.hanzi, Character.stroke_count).where(
                Character.hanzi.in_(wanted)
            )
        )
        return {row.hanzi: row.stroke_count for row in result}

    async def all_hanzi(self) -> tuple[str, ...]:
        """Every hanzi in the corpus, sorted by Unicode codepoint, cached.

        Used to hand the pack-generation agent the whole traceable set up front
        so it stops guessing characters and round-tripping to verify them.

        Sorted in Python (not ``ORDER BY``) so the order is pure codepoint order,
        independent of the database's collation/locale — a text ``ORDER BY`` on
        CJK can differ across collations, and the generation prompt relies on this
        block being byte-identical across calls for provider-side prompt caching.
        The result is memoized process-wide (:data:`_all_hanzi_cache`) because the
        corpus is static; ``reset_all_hanzi_cache`` clears it for tests.
        """
        global _all_hanzi_cache
        if _all_hanzi_cache is None:
            result = await self.session.execute(select(Character.hanzi))
            hanzi = tuple(sorted(result.scalars()))
            if not hanzi:
                # Corpus not yet imported: return the empty set WITHOUT caching,
                # so a generation racing deploy-time import doesn't pin an empty
                # corpus for the whole process. (missing_hanzi/stroke_counts
                # still query live.)
                return ()
            _all_hanzi_cache = hanzi
        return _all_hanzi_cache
