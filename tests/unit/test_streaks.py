from __future__ import annotations

from datetime import date, timedelta

import pytest

from habagou.domains.streaks import bucket_level, compute_streaks, next_milestone


@pytest.mark.workflow("WF-11")
def test_empty_history_has_no_streak_and_first_milestone() -> None:
    today = date(2026, 7, 5)

    streaks = compute_streaks({}, today=today)
    milestone = next_milestone(streaks.current)

    assert streaks.current == 0
    assert streaks.best == 0
    assert milestone.target_days == 7
    assert milestone.days_remaining == 7
    assert milestone.progress_pct == 0


@pytest.mark.workflow("WF-11")
def test_today_goal_met_extends_current_streak() -> None:
    today = date(2026, 7, 5)
    counts = {
        today - timedelta(days=2): 3,
        today - timedelta(days=1): 4,
        today: 3,
    }

    streaks = compute_streaks(counts, today=today)

    assert streaks.current == 3
    assert streaks.best == 3


@pytest.mark.workflow("WF-11")
def test_unfinished_today_anchors_current_streak_at_yesterday() -> None:
    today = date(2026, 7, 5)
    counts = {
        today - timedelta(days=2): 3,
        today - timedelta(days=1): 3,
        today: 2,
    }

    streaks = compute_streaks(counts, today=today)

    assert streaks.current == 2
    assert streaks.best == 2


@pytest.mark.workflow("WF-11")
def test_gap_breaks_current_streak() -> None:
    today = date(2026, 7, 5)
    counts = {
        today - timedelta(days=3): 3,
        today - timedelta(days=2): 0,
        today - timedelta(days=1): 3,
    }

    streaks = compute_streaks(counts, today=today)

    assert streaks.current == 1
    assert streaks.best == 1


@pytest.mark.workflow("WF-11")
def test_subtarget_days_do_not_count_toward_streak_but_bucket_to_levels() -> None:
    today = date(2026, 7, 5)
    counts = {
        today - timedelta(days=2): 3,
        today - timedelta(days=1): 2,
        today: 1,
    }

    streaks = compute_streaks(counts, today=today)

    assert streaks.current == 0
    assert streaks.best == 1
    assert bucket_level(1) == 1
    assert bucket_level(2) == 2


@pytest.mark.workflow("WF-11")
def test_best_streak_can_be_longer_than_current_old_run() -> None:
    today = date(2026, 7, 5)
    counts = {
        today - timedelta(days=10): 3,
        today - timedelta(days=9): 3,
        today - timedelta(days=8): 3,
        today - timedelta(days=1): 3,
    }

    streaks = compute_streaks(counts, today=today)

    assert streaks.current == 1
    assert streaks.best == 3


@pytest.mark.workflow("WF-11")
@pytest.mark.parametrize(
    ("current", "target", "remaining", "pct"),
    [
        (0, 7, 7, 0),
        (12, 14, 2, 86),
        (14, 30, 16, 47),
        (101, 150, 49, 67),
    ],
)
def test_next_milestone_ladder(
    current: int,
    target: int,
    remaining: int,
    pct: int,
) -> None:
    milestone = next_milestone(current)

    assert milestone.target_days == target
    assert milestone.days_remaining == remaining
    assert milestone.progress_pct == pct


@pytest.mark.workflow("WF-11")
@pytest.mark.parametrize(
    ("count", "level"),
    [
        (0, 0),
        (1, 1),
        (2, 2),
        (3, 3),
        (8, 3),
        (-1, 0),
    ],
)
def test_bucket_level_caps_between_zero_and_three(count: int, level: int) -> None:
    assert bucket_level(count) == level
