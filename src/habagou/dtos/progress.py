"""DTOs for progress API requests and responses."""

from __future__ import annotations

import datetime  # noqa: TC003 - Pydantic resolves schema annotations.

from pydantic import BaseModel, Field

from habagou.dtos.packs import PackProgressDTO  # noqa: TC001 - Pydantic schema.
from habagou.models import ActivityType  # noqa: TC001 - Pydantic validation.


class CompletionCreateDTO(BaseModel):
    pack_slug: str = Field(min_length=1)
    activity: ActivityType
    duration_ms: int = Field(ge=0)


class PackProgressResponseDTO(BaseModel):
    pack_slug: str
    progress: PackProgressDTO


class CompletionResponseDTO(PackProgressResponseDTO):
    activity: ActivityType
    duration_ms: int


class ProgressResetDTO(PackProgressResponseDTO):
    deleted_count: int


class DailyActivityDTO(BaseModel):
    date: datetime.date
    count: int
    level: int


class DailyGoalDTO(BaseModel):
    completed: int
    target: int


class NextMilestoneDTO(BaseModel):
    target_days: int
    days_remaining: int
    progress_pct: int


class ProgressSummaryDTO(BaseModel):
    current_streak: int
    best_streak: int
    daily_goal: DailyGoalDTO
    activity: list[DailyActivityDTO]
    next_milestone: NextMilestoneDTO
    characters_traced: int
    packs_completed: int
    packs_total: int
