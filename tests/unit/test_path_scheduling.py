from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from habagou.path_scheduling import (
    LADDER,
    UNIT_PHRASES,
    UNIT_STRIDE,
    Activity,
    CharacterSpec,
    Curriculum,
    ItemSpec,
    PackSpec,
    ReviewState,
    ReviewUnit,
    SentenceSpec,
    UnitType,
    apply_completion,
    generate_batch,
)

NOW = datetime(2026, 7, 12, 9, 0, tzinfo=UTC)


# --------------------------------------------------------------------------- #
# Fixtures / builders.
# --------------------------------------------------------------------------- #
def _char(hanzi: str, pinyin: str, meaning: str) -> CharacterSpec:
    return CharacterSpec(hanzi=hanzi, pinyin=pinyin, meaning=meaning)


def _pack(
    slug: str,
    *,
    title: str | None = None,
    chars: tuple[CharacterSpec, ...] = (),
    sentences: tuple[SentenceSpec, ...] = (),
) -> PackSpec:
    return PackSpec(
        slug=slug,
        title=title or slug.title(),
        glyph=chars[0].hanzi if chars else "字",
        color="#3f8a86",
        characters=chars,
        sentences=sentences,
    )


NUMBERS = _pack(
    "numbers",
    title="Numbers",
    chars=(
        _char("一", "yī", "one"),
        _char("二", "èr", "two"),
        _char("三", "sān", "three"),
    ),
    sentences=(
        SentenceSpec(ref="n-s1", hanzi="一二三", pinyin="yī èr sān", translation="123"),
    ),
)
GREETINGS = _pack(
    "greetings",
    title="Greetings",
    chars=(
        _char("你", "nǐ", "you"),
        _char("好", "hǎo", "good"),
    ),
)


def _state(
    pack_slug: str,
    unit_type: UnitType,
    unit_ref: str,
    activity: Activity,
    *,
    reps: int = 1,
    due_at: datetime | None = None,
    last_seen_at: datetime | None = None,
) -> ReviewState:
    return ReviewState(
        pack_slug=pack_slug,
        unit_type=unit_type,
        unit_ref=unit_ref,
        activity=activity,
        reps=reps,
        last_seen_at=last_seen_at,
        due_at=due_at,
    )


def _introduced(pack: PackSpec, *, due_at: datetime | None = None) -> list[ReviewState]:
    """A review state for every reviewable unit in a pack."""
    states: list[ReviewState] = []
    for char in pack.characters:
        states.append(
            _state(pack.slug, "character", char.hanzi, "trace", due_at=due_at)
        )
        states.append(
            _state(pack.slug, "character", char.hanzi, "match", due_at=due_at)
        )
    for sentence in pack.sentences:
        states.append(
            _state(pack.slug, "sentence", sentence.ref, "sentence", due_at=due_at)
        )
    return states


# --------------------------------------------------------------------------- #
# apply_completion — ladder progression + clamping (WF-13).
# --------------------------------------------------------------------------- #
@pytest.mark.workflow("WF-13")
def test_first_completion_schedules_one_day_out() -> None:
    state = _state("numbers", "character", "一", "trace", reps=0)

    updated = apply_completion(state, NOW)

    assert updated.reps == 1
    assert updated.last_seen_at == NOW
    assert updated.due_at == NOW + timedelta(days=LADDER[0])
    # Identity is preserved.
    assert updated.unit == ReviewUnit("numbers", "character", "一", "trace")


@pytest.mark.workflow("WF-13")
def test_completion_is_immutable() -> None:
    state = _state("numbers", "character", "一", "trace", reps=0)

    apply_completion(state, NOW)

    assert state.reps == 0
    assert state.due_at is None


@pytest.mark.workflow("WF-13")
@pytest.mark.parametrize(
    ("reps_before", "expected_days"),
    [
        (0, 1),
        (1, 3),
        (2, 7),
        (3, 14),
        (4, 30),
    ],
)
def test_ladder_progression(reps_before: int, expected_days: int) -> None:
    state = _state("numbers", "character", "一", "trace", reps=reps_before)

    updated = apply_completion(state, NOW)

    assert updated.reps == reps_before + 1
    assert updated.due_at == NOW + timedelta(days=expected_days)


@pytest.mark.workflow("WF-13")
@pytest.mark.parametrize("reps_before", [4, 5, 9, 40])
def test_ladder_clamps_at_top_rung(reps_before: int) -> None:
    state = _state("numbers", "character", "一", "trace", reps=reps_before)

    updated = apply_completion(state, NOW)

    assert updated.due_at == NOW + timedelta(days=LADDER[-1])


@pytest.mark.workflow("WF-13")
def test_repeated_completions_climb_then_hold() -> None:
    state = _state("numbers", "character", "一", "trace", reps=0)
    seen = []
    moment = NOW
    for _ in range(7):
        state = apply_completion(state, moment)
        assert state.due_at is not None
        seen.append((state.due_at - moment).days)
        moment = state.due_at
    assert seen == [1, 3, 7, 14, 30, 30, 30]


# --------------------------------------------------------------------------- #
# generate_batch — new material ordering (WF-13).
# --------------------------------------------------------------------------- #
@pytest.mark.workflow("WF-13")
def test_fresh_learner_starts_with_new_trace() -> None:
    curriculum = Curriculum(packs=(NUMBERS,))

    batch = generate_batch(curriculum, [], NOW)

    assert batch, "batch is never empty for a non-empty curriculum"
    first = batch[0]
    assert first.kind == "new"
    assert first.activity == "trace"
    assert first.pack.slug == "numbers"
    assert [c["hanzi"] for c in first.content["chars"]] == ["一", "二", "三"]


@pytest.mark.workflow("WF-13")
def test_new_material_order_trace_then_match_then_sentence() -> None:
    curriculum = Curriculum(packs=(NUMBERS,))

    batch = generate_batch(curriculum, [], NOW, batch_size=10)

    activities = [item.activity for item in batch]
    assert activities == ["trace", "match", "sentence"]
    assert all(item.kind == "new" for item in batch)
    # Match runs over the pack's recently-introduced characters.
    match_item = batch[1]
    assert [p["hanzi"] for p in match_item.content["pairs"]] == ["一", "二", "三"]
    # Sentence carries the whole-sentence content shape.
    sentence_item = batch[2]
    assert sentence_item.content == {
        "hanzi": "一二三",
        "pinyin": "yī èr sān",
        "translation": "123",
    }


@pytest.mark.workflow("WF-13")
def test_trace_items_chunk_two_to_three_chars() -> None:
    chars = tuple(_char(str(i), f"p{i}", f"m{i}") for i in range(7))
    curriculum = Curriculum(packs=(_pack("big", chars=chars),))

    batch = generate_batch(curriculum, [], NOW, batch_size=20)

    trace_items = [item for item in batch if item.activity == "trace"]
    sizes = [len(item.content["chars"]) for item in trace_items]
    assert sum(sizes) == 7
    assert all(2 <= size <= 3 for size in sizes)


@pytest.mark.workflow("WF-13")
def test_match_items_chunk_three_to_five_pairs() -> None:
    chars = tuple(_char(str(i), f"p{i}", f"m{i}") for i in range(9))
    curriculum = Curriculum(packs=(_pack("big", chars=chars),))

    batch = generate_batch(curriculum, [], NOW, batch_size=50)

    match_items = [item for item in batch if item.activity == "match"]
    sizes = [len(item.content["pairs"]) for item in match_items]
    assert sum(sizes) == 9
    assert all(3 <= size <= 5 for size in sizes)


@pytest.mark.workflow("WF-13")
def test_deterministic_curriculum_order_across_packs() -> None:
    curriculum = Curriculum(packs=(GREETINGS, NUMBERS))

    batch = generate_batch(curriculum, [], NOW, batch_size=50)

    # Every greetings item precedes every numbers item.
    slugs = [item.pack.slug for item in batch]
    assert slugs == sorted(slugs, key=lambda s: 0 if s == "greetings" else 1)
    assert slugs[0] == "greetings"
    assert "numbers" in slugs


@pytest.mark.workflow("WF-13")
def test_match_only_over_already_introduced_chars() -> None:
    curriculum = Curriculum(packs=(NUMBERS,))
    # 一 and 二 already introduced for match; only 三 is new for match.
    states = [
        _state("numbers", "character", "一", "match", due_at=NOW + timedelta(days=5)),
        _state("numbers", "character", "二", "match", due_at=NOW + timedelta(days=5)),
        _state("numbers", "character", "一", "trace", due_at=NOW + timedelta(days=5)),
        _state("numbers", "character", "二", "trace", due_at=NOW + timedelta(days=5)),
        _state("numbers", "character", "三", "trace", due_at=NOW + timedelta(days=5)),
    ]

    batch = generate_batch(curriculum, states, NOW, batch_size=50)

    new_match = [
        item for item in batch if item.activity == "match" and item.kind == "new"
    ]
    # Only 三 remains new for match, and a single pair can't form a match item.
    assert new_match == []


@pytest.mark.workflow("WF-13")
def test_pack_with_single_new_char_emits_no_match() -> None:
    curriculum = Curriculum(packs=(_pack("solo", chars=(_char("大", "dà", "big"),)),))

    batch = generate_batch(curriculum, [], NOW, batch_size=10)

    assert [item.activity for item in batch] == ["trace"]


# --------------------------------------------------------------------------- #
# generate_batch — reviews before new + oldest-due-first (WF-14).
# --------------------------------------------------------------------------- #
@pytest.mark.workflow("WF-14")
def test_due_reviews_come_before_new_material() -> None:
    curriculum = Curriculum(packs=(GREETINGS, NUMBERS))
    # Greetings fully introduced; its trace units are due.
    states = [
        _state("greetings", "character", "你", "trace", due_at=NOW - timedelta(days=1)),
        _state("greetings", "character", "好", "trace", due_at=NOW - timedelta(days=1)),
    ]

    batch = generate_batch(curriculum, states, NOW, batch_size=10)

    assert batch[0].kind == "review"
    assert batch[0].pack.slug == "greetings"
    assert batch[0].activity == "trace"
    # New material still follows.
    assert any(item.kind == "new" for item in batch)


@pytest.mark.workflow("WF-14")
def test_review_groups_same_pack_activity_into_one_item() -> None:
    curriculum = Curriculum(packs=(NUMBERS,))
    states = [
        _state("numbers", "character", "一", "trace", due_at=NOW - timedelta(days=2)),
        _state("numbers", "character", "二", "trace", due_at=NOW - timedelta(days=2)),
        _state("numbers", "character", "三", "trace", due_at=NOW - timedelta(days=2)),
    ]

    batch = generate_batch(curriculum, states, NOW, batch_size=10)

    review = [item for item in batch if item.kind == "review"]
    assert len(review) == 1
    assert [c["hanzi"] for c in review[0].content["chars"]] == ["一", "二", "三"]
    assert review[0].units == (
        ReviewUnit("numbers", "character", "一", "trace"),
        ReviewUnit("numbers", "character", "二", "trace"),
        ReviewUnit("numbers", "character", "三", "trace"),
    )


@pytest.mark.workflow("WF-14")
def test_reviews_ordered_oldest_due_first() -> None:
    curriculum = Curriculum(packs=(NUMBERS, GREETINGS))
    states = [
        # Numbers trace due 5 days ago (oldest).
        _state("numbers", "character", "一", "trace", due_at=NOW - timedelta(days=5)),
        # Greetings trace due 1 day ago (newer).
        _state("greetings", "character", "你", "trace", due_at=NOW - timedelta(days=1)),
    ]

    batch = generate_batch(curriculum, states, NOW, batch_size=10)

    reviews = [item for item in batch if item.kind == "review"]
    assert [item.pack.slug for item in reviews] == ["numbers", "greetings"]


@pytest.mark.workflow("WF-14")
def test_not_yet_due_units_are_not_reviewed() -> None:
    curriculum = Curriculum(packs=(NUMBERS,))
    states = _introduced(NUMBERS, due_at=NOW + timedelta(days=3))

    batch = generate_batch(curriculum, states, NOW, batch_size=10)

    # Everything introduced and nothing due -> exhaustion early-review, but no
    # unit is *past* due, so all items are the resurfacing kind.
    assert all(item.kind == "review" for item in batch)


@pytest.mark.workflow("WF-14")
def test_sentence_tracked_as_whole_unit() -> None:
    curriculum = Curriculum(packs=(NUMBERS,))
    states = [
        _state(
            "numbers", "sentence", "n-s1", "sentence", due_at=NOW - timedelta(days=1)
        ),
    ]

    batch = generate_batch(curriculum, states, NOW, batch_size=10)

    review = [item for item in batch if item.kind == "review"]
    assert len(review) == 1
    assert review[0].activity == "sentence"
    assert review[0].units == (ReviewUnit("numbers", "sentence", "n-s1", "sentence"),)
    assert review[0].content == {
        "hanzi": "一二三",
        "pinyin": "yī èr sān",
        "translation": "123",
    }


@pytest.mark.workflow("WF-14")
def test_completed_unit_resurfaces_once_due() -> None:
    curriculum = Curriculum(packs=(NUMBERS,))
    # A learner completes 一-trace; it comes due later.
    completed = apply_completion(
        _state("numbers", "character", "一", "trace", reps=0), NOW
    )
    assert completed.due_at is not None
    later = completed.due_at + timedelta(hours=1)

    batch = generate_batch(curriculum, [completed], later, batch_size=10)

    review = [item for item in batch if item.kind == "review"]
    assert any(
        ReviewUnit("numbers", "character", "一", "trace") in item.units
        for item in review
    )


# --------------------------------------------------------------------------- #
# generate_batch — exhaustion / never empty (WF-14).
# --------------------------------------------------------------------------- #
@pytest.mark.workflow("WF-14")
def test_exhaustion_yields_early_review_not_empty() -> None:
    curriculum = Curriculum(packs=(NUMBERS,))
    states = _introduced(NUMBERS, due_at=NOW + timedelta(days=10))

    batch = generate_batch(curriculum, states, NOW, batch_size=10)

    assert batch, "the Path never ends"
    assert all(item.kind == "review" for item in batch)


@pytest.mark.workflow("WF-14")
def test_exhaustion_prefers_soonest_due_units() -> None:
    curriculum = Curriculum(packs=(NUMBERS, GREETINGS))
    # Everything introduced (no new material); greetings comes due soonest.
    states = [
        *_introduced(NUMBERS, due_at=NOW + timedelta(days=9)),
        *_introduced(GREETINGS, due_at=NOW + timedelta(days=2)),
    ]

    batch = generate_batch(curriculum, states, NOW, batch_size=1)

    assert len(batch) == 1
    assert batch[0].kind == "review"
    assert batch[0].pack.slug == "greetings"


@pytest.mark.workflow("WF-14")
def test_empty_curriculum_yields_empty_batch() -> None:
    assert generate_batch(Curriculum(packs=()), [], NOW) == []


# --------------------------------------------------------------------------- #
# generate_batch — kind assignment (WF-13/WF-14).
# --------------------------------------------------------------------------- #
@pytest.mark.workflow("WF-13")
def test_kind_new_for_unseen_units() -> None:
    curriculum = Curriculum(packs=(NUMBERS,))

    batch = generate_batch(curriculum, [], NOW, batch_size=10)

    assert all(item.kind == "new" for item in batch)


@pytest.mark.workflow("WF-14")
def test_kind_review_for_seen_and_due_units() -> None:
    curriculum = Curriculum(packs=(NUMBERS,))
    states = [
        _state("numbers", "character", "一", "trace", due_at=NOW - timedelta(days=1)),
        _state("numbers", "character", "二", "trace", due_at=NOW - timedelta(days=1)),
    ]

    batch = generate_batch(curriculum, states, NOW, batch_size=10)

    assert batch[0].kind == "review"


# --------------------------------------------------------------------------- #
# Unit labels (WF-13).
# --------------------------------------------------------------------------- #
@pytest.mark.workflow("WF-13")
def test_only_first_item_carries_a_unit_label() -> None:
    curriculum = Curriculum(packs=(NUMBERS,))

    batch = generate_batch(curriculum, [], NOW, batch_size=10)

    assert batch[0].unit_label == "UNIT 1 · WARMING UP"
    assert all(item.unit_label is None for item in batch[1:])


@pytest.mark.workflow("WF-13")
def test_unit_label_advances_with_progress() -> None:
    curriculum = Curriculum(packs=(NUMBERS,))
    # Enough introduced units to cross into the second unit label.
    states = _introduced(NUMBERS, due_at=NOW - timedelta(days=1))
    assert len(states) >= UNIT_STRIDE

    batch = generate_batch(curriculum, states, NOW, batch_size=10)

    expected_index = len(states) // UNIT_STRIDE
    expected_phrase = UNIT_PHRASES[expected_index % len(UNIT_PHRASES)]
    expected = f"UNIT {expected_index + 1} · {expected_phrase}"
    assert batch[0].unit_label == expected
    assert batch[0].unit_label != "UNIT 1 · WARMING UP"


# --------------------------------------------------------------------------- #
# Determinism / idempotence (WF-13).
# --------------------------------------------------------------------------- #
@pytest.mark.workflow("WF-13")
def test_same_inputs_produce_identical_batch() -> None:
    curriculum = Curriculum(packs=(GREETINGS, NUMBERS))
    states = [
        _state("greetings", "character", "你", "trace", due_at=NOW - timedelta(days=1)),
    ]

    first = generate_batch(curriculum, states, NOW, batch_size=6)
    second = generate_batch(curriculum, list(states), NOW, batch_size=6)

    assert first == second


@pytest.mark.workflow("WF-13")
def test_batch_size_bounds_item_count() -> None:
    chars = tuple(_char(str(i), f"p{i}", f"m{i}") for i in range(20))
    curriculum = Curriculum(packs=(_pack("big", chars=chars),))

    batch = generate_batch(curriculum, [], NOW, batch_size=3)

    assert len(batch) == 3


@pytest.mark.workflow("WF-13")
def test_item_content_matches_activity_shape() -> None:
    curriculum = Curriculum(packs=(NUMBERS,))

    batch = generate_batch(curriculum, [], NOW, batch_size=10)

    for item in batch:
        assert isinstance(item, ItemSpec)
        if item.activity == "trace":
            assert set(item.content) == {"chars"}
        elif item.activity == "match":
            assert set(item.content) == {"pairs"}
        else:
            assert set(item.content) == {"hanzi", "pinyin", "translation"}
