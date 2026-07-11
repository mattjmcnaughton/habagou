"""Check production data invariants for a seeded Habagou database."""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from time import perf_counter
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from habagou.events import emit_workflow_event
from habagou.models import (
    ActivityCompletion,
    Character,
    Pack,
    PackCharacter,
    PackStatus,
    User,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True)
class InvariantViolation:
    code: str
    message: str


async def check_invariants(dsn: str) -> list[InvariantViolation]:
    """Return all data invariant violations for the database at dsn."""
    engine = create_async_engine(dsn)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessionmaker() as session:
            characters = set((await session.scalars(select(Character.hanzi))).all())
            packs = (
                await session.scalars(
                    select(Pack)
                    .where(Pack.status == PackStatus.PUBLISHED)
                    .options(
                        selectinload(Pack.characters).selectinload(
                            PackCharacter.character
                        ),
                        selectinload(Pack.sentences),
                    )
                )
            ).all()
            completions_missing_users = (
                await session.execute(
                    select(ActivityCompletion.id, ActivityCompletion.user_id)
                    .outerjoin(User, ActivityCompletion.user_id == User.id)
                    .where(User.id.is_(None))
                )
            ).all()
            completions_missing_packs = (
                await session.execute(
                    select(ActivityCompletion.id, ActivityCompletion.pack_id)
                    .outerjoin(Pack, ActivityCompletion.pack_id == Pack.id)
                    .where(Pack.id.is_(None))
                )
            ).all()
    finally:
        await engine.dispose()

    violations: list[InvariantViolation] = []
    for pack in packs:
        for pack_character in pack.characters:
            if pack_character.character is None:
                violations.append(
                    InvariantViolation(
                        code="missing_pack_character",
                        message=(
                            "published pack references missing corpus character: "
                            f"pack={pack.slug} "
                            f"character_id={pack_character.character_id}"
                        ),
                    )
                )
                continue
            hanzi = pack_character.character.hanzi
            if hanzi not in characters:
                violations.append(
                    InvariantViolation(
                        code="missing_pack_character",
                        message=(
                            "published pack references missing corpus character: "
                            f"pack={pack.slug} character={hanzi}"
                        ),
                    )
                )

        for sentence in pack.sentences:
            for hanzi in sentence.hanzi:
                if hanzi not in characters:
                    violations.append(
                        InvariantViolation(
                            code="missing_sentence_character",
                            message=(
                                "published pack sentence references missing corpus "
                                f"character: pack={pack.slug} character={hanzi} "
                                f"sentence={sentence.hanzi}"
                            ),
                        ),
                    )

    for completion_id, user_id in completions_missing_users:
        violations.append(
            InvariantViolation(
                code="dangling_completion_user",
                message=(
                    "activity completion references missing user: "
                    f"completion_id={completion_id} user_id={user_id}"
                ),
            )
        )

    for completion_id, pack_id in completions_missing_packs:
        violations.append(
            InvariantViolation(
                code="dangling_completion_pack",
                message=(
                    "activity completion references missing pack: "
                    f"completion_id={completion_id} pack_id={pack_id}"
                ),
            )
        )

    return violations


async def run(dsn: str) -> int:
    started = perf_counter()
    violations = await check_invariants(dsn)
    duration_ms = int((perf_counter() - started) * 1000)
    emit_workflow_event(
        "invariant_check",
        workflow="WF-10",
        outcome="error" if violations else "ok",
        duration_ms=duration_ms,
        issue_count=len(violations),
    )
    if not violations:
        print("invariant check passed")
        return 0

    print("invariant check failed", file=sys.stderr)
    for violation in violations:
        print(f"- {violation.code}: {violation.message}", file=sys.stderr)
    return 1


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True, help="SQLAlchemy database URL to check")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    return asyncio.run(run(args.dsn))


if __name__ == "__main__":
    raise SystemExit(main())
