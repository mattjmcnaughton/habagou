from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete

from habagou import db
from habagou.models import (
    ActivityCompletion,
    ActivityType,
    CompletionSource,
    Pack,
    PathItemKind,
    ReviewUnitType,
    User,
)
from habagou.repositories import (
    CharacterRepository,
    PackCharacterInput,
    PackRepository,
    PackSentenceInput,
    PathRepository,
    ProgressRepository,
    ReviewStateRepository,
    UserRepository,
)
from tests.integration.conftest import create_user, pack_by_slug


@pytest.mark.anyio
async def test_pack_repository_lists_visible_packs_with_counts() -> None:
    async with db.async_session() as session:
        user = await create_user(session, username="visible-user")
        other = await create_user(session, username="visible-other", email=None)
        await session.flush()
        session.add_all(
            [
                Pack(
                    slug="own-visible",
                    title="Own Visible",
                    glyph="私",
                    color="#444444",
                    sort_order=50,
                    owner_id=user.id,
                ),
                Pack(
                    slug="foreign-visible",
                    title="Foreign Visible",
                    glyph="他",
                    color="#555555",
                    sort_order=51,
                    owner_id=other.id,
                ),
            ]
        )
        await session.flush()

        repository = PackRepository(session)
        packs = await repository.list_visible(user_id=user.id)

    slugs = {item.pack.slug for item in packs}
    seeded = [item for item in packs if item.pack.slug in _seed_slugs()]

    # Own packs are visible (regardless of status); foreign owned packs are not.
    assert "own-visible" in slugs
    assert "foreign-visible" not in slugs
    assert [item.pack.slug for item in seeded] == [
        "greetings",
        "numbers",
        "family",
        "food-drink",
    ]
    assert [item.character_count for item in seeded] == [5, 5, 5, 5]
    assert [item.sentence_count for item in seeded] == [3, 2, 2, 2]


@pytest.mark.anyio
async def test_pack_repository_gets_pack_by_id_eager_loaded() -> None:
    async with db.async_session() as session:
        repository = PackRepository(session)
        greetings = await pack_by_slug(session, "greetings")
        assert greetings is not None

        pack = await repository.get_by_id(greetings.id)

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
async def test_pack_repository_get_visible_scopes_by_ownership() -> None:
    async with db.async_session() as session:
        owner = await create_user(session, username="visible-owner")
        other = await create_user(session, username="visible-stranger", email=None)
        await session.flush()

        global_pack = await pack_by_slug(session, "greetings")
        assert global_pack is not None
        owned_pack = Pack(
            slug="owner-scoped",
            title="Owner Scoped",
            glyph="私",
            color="#123456",
            sort_order=60,
            owner_id=owner.id,
        )
        session.add(owned_pack)
        await session.flush()

        repository = PackRepository(session)

        # Global packs are visible to anyone.
        global_for_owner = await repository.get_visible(global_pack.id, owner.id)
        global_for_other = await repository.get_visible(global_pack.id, other.id)
        assert global_for_owner is not None
        assert global_for_owner.id == global_pack.id
        assert global_for_other is not None
        assert global_for_other.id == global_pack.id

        # Owned packs are visible only to their owner.
        owned_for_owner = await repository.get_visible(owned_pack.id, owner.id)
        assert owned_for_owner is not None
        assert owned_for_owner.id == owned_pack.id
        assert await repository.get_visible(owned_pack.id, other.id) is None

        # Unknown ids resolve to nothing.
        assert await repository.get_visible(uuid.uuid4(), owner.id) is None


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
        pack = await pack_by_slug(session, "greetings")
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
        pack = await pack_by_slug(session, "greetings")
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


@pytest.mark.anyio
async def test_path_repository_appends_pages_and_counts_pending() -> None:
    async with db.async_session() as session:
        user = await create_user(session)
        pack = await pack_by_slug(session, "greetings")
        assert pack is not None

        repository = PathRepository(session)
        assert await repository.max_position(user_id=user.id) is None

        first = await repository.append(
            user_id=user.id,
            position=1,
            activity=ActivityType.TRACE,
            kind=PathItemKind.NEW,
            pack_id=pack.id,
            content={"trace": {"chars": [{"hanzi": "你"}]}},
        )
        await repository.append(
            user_id=user.id,
            position=2,
            activity=ActivityType.MATCH,
            kind=PathItemKind.REVIEW,
            pack_id=pack.id,
            content={"match": {"pairs": []}},
        )

        assert await repository.max_position(user_id=user.id) == 2
        assert await repository.count_pending(user_id=user.id) == 2

        # Completing the first item removes it from the pending count.
        await ProgressRepository(session).record(
            user_id=user.id,
            pack_id=pack.id,
            activity=ActivityType.TRACE,
            duration_ms=100,
            source=CompletionSource.PATH,
            path_item_id=first.id,
        )
        assert await repository.count_pending(user_id=user.id) == 1

        fetched = await repository.get_by_id(first.id)
        assert fetched is not None
        assert fetched.content == {"trace": {"chars": [{"hanzi": "你"}]}}

        after = await repository.list_for_user(user_id=user.id, after_position=1)
        assert [item.position for item in after] == [2]
        limited = await repository.list_for_user(user_id=user.id, limit=1)
        assert [item.position for item in limited] == [1]


@pytest.mark.anyio
async def test_review_state_repository_upserts_and_lists() -> None:
    async with db.async_session() as session:
        user = await create_user(session)
        pack = await pack_by_slug(session, "greetings")
        assert pack is not None

        repository = ReviewStateRepository(session)
        base = datetime(2026, 7, 10, tzinfo=UTC)
        created = await repository.upsert(
            user_id=user.id,
            pack_id=pack.id,
            unit_type=ReviewUnitType.CHARACTER,
            unit_ref="你",
            activity=ActivityType.TRACE,
            reps=1,
            last_seen_at=base,
            due_at=base + timedelta(days=1),
        )
        assert created.reps == 1

        # Upsert on the same identity mutates the existing row rather than
        # inserting a duplicate.
        updated = await repository.upsert(
            user_id=user.id,
            pack_id=pack.id,
            unit_type=ReviewUnitType.CHARACTER,
            unit_ref="你",
            activity=ActivityType.TRACE,
            reps=2,
            last_seen_at=base + timedelta(days=1),
            due_at=base + timedelta(days=4),
        )
        assert updated.reps == 2

        # A different activity for the same character is a distinct unit.
        await repository.upsert(
            user_id=user.id,
            pack_id=pack.id,
            unit_type=ReviewUnitType.CHARACTER,
            unit_ref="你",
            activity=ActivityType.MATCH,
            reps=1,
            last_seen_at=base,
            due_at=base + timedelta(days=1),
        )

        fetched = await repository.get(
            user_id=user.id,
            pack_id=pack.id,
            unit_type=ReviewUnitType.CHARACTER,
            unit_ref="你",
            activity=ActivityType.TRACE,
        )
        assert fetched is not None
        assert fetched.reps == 2

        listed = await repository.list_for_user(user_id=user.id)
        assert len(listed) == 2


@pytest.mark.anyio
async def test_per_pack_aggregate_excludes_path_completions() -> None:
    async with db.async_session() as session:
        user = await create_user(session)
        pack = await pack_by_slug(session, "greetings")
        assert pack is not None

        progress = ProgressRepository(session)
        await progress.delete_by_user_pack(user_id=user.id, pack_id=pack.id)

        item = await PathRepository(session).append(
            user_id=user.id,
            position=1,
            activity=ActivityType.TRACE,
            kind=PathItemKind.NEW,
            pack_id=pack.id,
            content={"trace": {"chars": []}},
        )
        # A path completion must not count toward whole-pack badges.
        await progress.record(
            user_id=user.id,
            pack_id=pack.id,
            activity=ActivityType.TRACE,
            duration_ms=100,
            source=CompletionSource.PATH,
            path_item_id=item.id,
        )

        path_only = await progress.per_pack_aggregate(user_id=user.id, pack_id=pack.id)
        assert path_only[ActivityType.TRACE].completed is False
        assert path_only[ActivityType.TRACE].completion_count == 0

        # A whole-pack completion does count.
        await progress.record(
            user_id=user.id,
            pack_id=pack.id,
            activity=ActivityType.TRACE,
            duration_ms=200,
        )
        with_pack = await progress.per_pack_aggregate(user_id=user.id, pack_id=pack.id)
        assert with_pack[ActivityType.TRACE].completed is True
        assert with_pack[ActivityType.TRACE].completion_count == 1
        assert with_pack[ActivityType.TRACE].best_duration_ms == 200


@pytest.mark.anyio
async def test_pack_owner_id_round_trips_global_and_owned() -> None:
    async with db.async_session() as session:
        user = await create_user(session)

        global_pack = Pack(
            slug="owner-global",
            title="Global Pack",
            glyph="全",
            color="#111111",
            sort_order=0,
        )
        owned_pack = Pack(
            slug="owner-private",
            title="Private Pack",
            glyph="私",
            color="#222222",
            sort_order=0,
            owner_id=user.id,
        )
        session.add_all([global_pack, owned_pack])
        await session.flush()

        global_reloaded = await session.get(Pack, global_pack.id)
        owned_reloaded = await session.get(Pack, owned_pack.id)

    assert global_reloaded is not None
    assert global_reloaded.owner_id is None
    assert owned_reloaded is not None
    assert owned_reloaded.owner_id == user.id


@pytest.mark.anyio
async def test_seeded_packs_have_null_owner_id() -> None:
    async with db.async_session() as session:
        user = await create_user(session, username="null-owner-check")
        await session.flush()
        packs = await PackRepository(session).list_visible(user_id=user.id)

    seeded = [item for item in packs if item.pack.slug in _seed_slugs()]
    assert len(seeded) == 4
    assert all(item.pack.owner_id is None for item in seeded)


@pytest.mark.anyio
async def test_deleting_user_cascades_owned_packs_but_spares_global() -> None:
    async with db.async_session() as session:
        user = await create_user(session)
        owned_pack = Pack(
            slug="cascade-owned",
            title="Owned Pack",
            glyph="私",
            color="#333333",
            sort_order=0,
            owner_id=user.id,
        )
        global_pack = Pack(
            slug="cascade-global",
            title="Global Pack",
            glyph="全",
            color="#444444",
            sort_order=0,
        )
        session.add_all([owned_pack, global_pack])
        await session.commit()
        user_id = user.id
        owned_id = owned_pack.id
        global_id = global_pack.id

    async with db.async_session() as session:
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()

    async with db.async_session() as session:
        # CASCADE removes the owner's private pack; the global pack is untouched.
        assert await session.get(Pack, owned_id) is None
        assert await session.get(Pack, global_id) is not None


@pytest.mark.anyio
async def test_pack_repository_create_persists_owned_pack() -> None:
    async with db.async_session() as session:
        user = await create_user(session)
        repository = PackRepository(session)

        created = await repository.create(
            owner_id=user.id,
            slug="owned-create",
            title="Owned Create",
            glyph="创",
            color="#abcdef",
            sort_order=7,
            characters=[
                PackCharacterInput(hanzi="你", pinyin="nǐ", meaning="you"),
                PackCharacterInput(hanzi="好", pinyin="hǎo", meaning="good"),
            ],
            sentences=[
                PackSentenceInput(hanzi="你好", pinyin="nǐ hǎo", translation="Hello"),
            ],
        )
        await session.flush()

        fetched = await pack_by_slug(session, "owned-create")

    assert created.owner_id == user.id
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.owner_id == user.id
    assert fetched.title == "Owned Create"
    assert fetched.glyph == "创"
    assert fetched.color == "#abcdef"
    assert fetched.sort_order == 7
    assert [
        (link.position, link.character.hanzi, link.pinyin, link.meaning)
        for link in fetched.characters
    ] == [
        (1, "你", "nǐ", "you"),
        (2, "好", "hǎo", "good"),
    ]
    assert [
        (sentence.position, sentence.hanzi, sentence.pinyin, sentence.translation)
        for sentence in fetched.sentences
    ] == [
        (1, "你好", "nǐ hǎo", "Hello"),
    ]


def _seed_slugs() -> set[str]:
    return {"greetings", "numbers", "family", "food-drink"}
