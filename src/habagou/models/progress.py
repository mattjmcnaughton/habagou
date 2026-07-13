"""Activity completion event ORM model."""

from __future__ import annotations

import uuid  # noqa: TC003 - SQLAlchemy resolves mapped annotations at runtime.
from datetime import (
    datetime,  # noqa: TC003 - SQLAlchemy resolves mapped annotations at runtime.
)
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from habagou.db import Base
from habagou.models.enums import ActivityType, CompletionSource

if TYPE_CHECKING:
    from habagou.models.packs import Pack
    from habagou.models.path import PathItem
    from habagou.models.users import User


class ActivityCompletion(Base):
    """Append-only activity completion event."""

    __tablename__ = "activity_completions"
    __table_args__ = (
        Index("ix_activity_completions_user_pack", "user_id", "pack_id"),
        CheckConstraint(
            "source <> 'path' OR path_item_id IS NOT NULL",
            name="ck_activity_completions_path_source",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    pack_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("packs.id", ondelete="CASCADE"),
        nullable=False,
    )
    activity: Mapped[ActivityType] = mapped_column(
        Enum(
            ActivityType,
            name="activity_type",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
    )
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[CompletionSource] = mapped_column(
        Enum(
            CompletionSource,
            name="completion_source",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
        default=CompletionSource.PACK,
    )
    path_item_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("path_items.id", ondelete="CASCADE"),
        nullable=True,
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="completions")
    pack: Mapped[Pack] = relationship(back_populates="completions")
    path_item: Mapped[PathItem | None] = relationship(back_populates="completions")
