"""Spaced-repetition review state ORM model."""

from __future__ import annotations

import uuid  # noqa: TC003 - SQLAlchemy resolves mapped annotations at runtime.
from datetime import (
    datetime,  # noqa: TC003 - SQLAlchemy resolves mapped annotations at runtime.
)

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from habagou.db import Base
from habagou.models.enums import ActivityType, ReviewUnitType


class ReviewState(Base):
    """Spaced-repetition state for one reviewable unit.

    Derived cache over the append-only completion event log: updated
    transactionally on completion and fully rebuildable by replaying events
    (see ADR-0008). Identity is the five-column tuple
    ``(user, pack, unit_type, unit_ref, activity)``.
    """

    __tablename__ = "review_states"
    __table_args__ = (Index("ix_review_states_user_due", "user_id", "due_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    pack_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("packs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    unit_type: Mapped[ReviewUnitType] = mapped_column(
        Enum(
            ReviewUnitType,
            name="review_unit_type",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        primary_key=True,
    )
    unit_ref: Mapped[str] = mapped_column(String, primary_key=True)
    activity: Mapped[ActivityType] = mapped_column(
        Enum(
            ActivityType,
            name="activity_type",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        primary_key=True,
    )
    reps: Mapped[int] = mapped_column(Integer, nullable=False)
    # Nullable: a reviewable unit is recorded at generation time with
    # ``reps=0, last_seen_at=None, due_at=None`` ("introduced, not yet
    # practiced"). ``apply_completion`` populates both on first completion.
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
