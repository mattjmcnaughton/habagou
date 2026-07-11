from __future__ import annotations

from datetime import UTC, datetime

import pytest

from habagou import db
from habagou.models import (
    ActivityCompletion,
    ActivityType,
    Pack,
    PackStatus,
)
from habagou.repositories import (
    CharacterRepository,
    PackRepository,
    ProgressRepository,
    UserRepository,
)
from tests.integration.conftest import create_user


@pytest.mark.anyio
async def test_pack_repository_lists_published_packs_with_counts() -> None:
    async with db.async_session() as session:
        session.add(
            Pack(
                slug="repository-draft",
                title="Repository Draft",
                glyph="草",
                color="#444444",
                status=PackStatus.DRAFT,
                sort_order=0,
            )
        )
        await session.flush()

        repository = PackRepository(session)
        packs = await repository.list_published()

    seeded = [item for item in packs if item.pack.slug in _seed_slugs()]

    assert "repository-draft" not in {item.pack.slug for item in packs}
    assert [item.pack.slug for item in seeded] == [
        "greetings",
        "numbers",
        "family",
        "food-drink",
    ]
    assert [item.character_count for item in seeded] == [5, 5, 5, 5]
    assert [item.sentence_count for item in seeded] == [3, 2, 2, 2]


@pytest.mark.anyio
async def test_pack_repository_gets_pack_by_slug_eager_loaded() -> None:
    async with db.async_session() as session:
        repository = PackRepository(session)
        pack = await repository.get_by_slug("greetings")

    assert pack is not None
    assert pack.title == "Greetings"
    assert [link.character.hanzi for link in pack.characters] == [
        "你",
        "好",
        "我",
        "他",
        "谢",
    ]
    assert [sentence.hanzi for sentence in pack.sentences] == [
        "你好",
        "我很好",
        "谢谢你",
    ]


@pytest.mark.anyio
async def test_character_repository_reads_strokes_and_missing_set() -> None:
    async with db.async_session() as session:
        repository = CharacterRepository(session)
        strokes = await repository.strokes_by_hanzi("你")
        missing = await repository.missing_hanzi({"你", "好", "☂"})
        empty_missing = await repository.missing_hanzi(set())

    assert strokes is not None
    assert isinstance(strokes["strokes"], list)
    assert missing == {"☂"}
    assert empty_missing == set()


@pytest.mark.anyio
async def test_progress_repository_records_aggregates_and_deletes() -> None:
    async with db.async_session() as session:
        user = await create_user(session)
        pack = await PackRepository(session).get_by_slug("greetings")
        assert pack is not None

        repository = ProgressRepository(session)
        await repository.delete_by_user_pack(user_id=user.id, pack_id=pack.id)
        await session.flush()

        empty = await repository.per_pack_aggregate(user_id=user.id, pack_id=pack.id)
        assert empty[ActivityType.TRACE].completed is False
        assert empty[ActivityType.TRACE].completion_count == 0
        assert empty[ActivityType.TRACE].best_duration_ms is None

        first = await repository.record(
            user_id=user.id,
            pack_id=pack.id,
            activity=ActivityType.TRACE,
            duration_ms=1200,
        )
        second = await repository.record(
            user_id=user.id,
            pack_id=pack.id,
            activity=ActivityType.TRACE,
            duration_ms=800,
        )
        await repository.record(
            user_id=user.id,
            pack_id=pack.id,
            activity=ActivityType.MATCH,
            duration_ms=1500,
        )
        assert first.id != second.id

        aggregate = await repository.per_pack_aggregate(
            user_id=user.id, pack_id=pack.id
        )
        assert aggregate[ActivityType.TRACE].completed is True
        assert aggregate[ActivityType.TRACE].completion_count == 2
        assert aggregate[ActivityType.TRACE].best_duration_ms == 800
        assert aggregate[ActivityType.MATCH].completed is True
        assert aggregate[ActivityType.MATCH].completion_count == 1
        assert aggregate[ActivityType.SENTENCE].completed is False

        deleted = await repository.delete_by_user_pack(user_id=user.id, pack_id=pack.id)
        await session.flush()

        reset = await repository.per_pack_aggregate(user_id=user.id, pack_id=pack.id)

    assert deleted == 3
    assert all(not progress.completed for progress in reset.values())


@pytest.mark.workflow("WF-11")
@pytest.mark.anyio
async def test_progress_repository_groups_daily_counts_by_timezone_offset() -> None:
    async with db.async_session() as session:
        user = await create_user(session)
        pack = await PackRepository(session).get_by_slug("greetings")
        assert pack is not None

        repository = ProgressRepository(session)
        await repository.delete_by_user_pack(user_id=user.id, pack_id=pack.id)
        session.add_all(
            [
                ActivityCompletion(
                    user_id=user.id,
                    pack_id=pack.id,
                    activity=ActivityType.TRACE,
                    duration_ms=1000,
                    completed_at=datetime(2026, 7, 5, 1, 30, tzinfo=UTC),
                ),
                ActivityCompletion(
                    user_id=user.id,
                    pack_id=pack.id,
                    activity=ActivityType.MATCH,
                    duration_ms=1000,
                    completed_at=datetime(2026, 7, 5, 12, 0, tzinfo=UTC),
                ),
            ]
        )
        await session.flush()

        utc_counts = await repository.daily_completion_counts(
            user_id=user.id,
            tz_offset_minutes=0,
        )
        eastern_counts = await repository.daily_completion_counts(
            user_id=user.id,
            tz_offset_minutes=300,
        )

    assert utc_counts == {datetime(2026, 7, 5, tzinfo=UTC).date(): 2}
    assert eastern_counts == {
        datetime(2026, 7, 4, tzinfo=UTC).date(): 1,
        datetime(2026, 7, 5, tzinfo=UTC).date(): 1,
    }


@pytest.mark.anyio
async def test_user_repository_round_trips_identity() -> None:
    async with db.async_session() as session:
        repository = UserRepository(session)
        created = await repository.create(
            username="identity-user",
            display_name="Identity User",
            auth_issuer="https://issuer.example.test",
            auth_subject="subject-1",
            email="identity@example.com",
        )
        await session.flush()

        found = await repository.get_by_identity(
            "https://issuer.example.test", "subject-1"
        )
        username_exists = await repository.username_exists("identity-user")

    assert found is created
    assert username_exists is True


def _seed_slugs() -> set[str]:
    return {"greetings", "numbers", "family", "food-drink"}
