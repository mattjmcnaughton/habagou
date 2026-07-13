"""Pure progress streak calculations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

DAILY_GOAL_TARGET = 3
MILESTONES = (7, 14, 30, 60, 100)


@dataclass(frozen=True)
class Streaks:
    current: int
    best: int


@dataclass(frozen=True)
class Milestone:
    target_days: int
    days_remaining: int
    progress_pct: int


def bucket_level(count: int) -> int:
    """Return the heatmap level for a completion count."""
    return max(0, min(count, DAILY_GOAL_TARGET))


def compute_streaks(daily_counts: Mapping[date, int], *, today: date) -> Streaks:
    goal_days = {
        day for day, count in daily_counts.items() if count >= DAILY_GOAL_TARGET
    }
    if not goal_days:
        return Streaks(current=0, best=0)

    anchor = today if today in goal_days else today - timedelta(days=1)
    current = _run_ending_at(goal_days, anchor)
    return Streaks(current=current, best=_best_run(goal_days))


def next_milestone(current_streak: int) -> Milestone:
    target = next(
        (milestone for milestone in MILESTONES if milestone > current_streak),
        _next_fifty(current_streak),
    )
    return Milestone(
        target_days=target,
        days_remaining=target - current_streak,
        progress_pct=round(100 * current_streak / target),
    )


def _run_ending_at(goal_days: set[date], day: date) -> int:
    length = 0
    current = day
    while current in goal_days:
        length += 1
        current -= timedelta(days=1)
    return length


def _best_run(goal_days: set[date]) -> int:
    best = 0
    current = 0
    previous: date | None = None
    for day in sorted(goal_days):
        if previous is not None and day == previous + timedelta(days=1):
            current += 1
        else:
            current = 1
        best = max(best, current)
        previous = day
    return best


def _next_fifty(current_streak: int) -> int:
    return ((current_streak // 50) + 1) * 50
