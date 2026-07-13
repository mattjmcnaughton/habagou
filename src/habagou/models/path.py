"""Learning Path item ORM model."""

from __future__ import annotations

import uuid
from datetime import (
    datetime,  # noqa: TC003 - SQLAlchemy resolves mapped annotations at runtime.
)
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from habagou.db import Base
from habagou.models.enums import ActivityType, PathItemKind

if TYPE_CHECKING:
    from habagou.models.packs import Pack
    from habagou.models.progress import ActivityCompletion


class PathItem(Base):
    """Materialized, append-only lesson in a learner's Path.

    Created by the generator and never mutated or deleted. Display state
    (done/current/locked) is derived at read time, not stored. The lesson's
    content snapshot is pinned in the ``content`` JSONB column at generation
    time.
    """

    __tablename__ = "path_items"
    __table_args__ = (
        UniqueConstraint("user_id", "position", name="uq_path_items_user_position"),
        Index("ix_path_items_user", "user_id", "position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    activity: Mapped[ActivityType] = mapped_column(
        Enum(
            ActivityType,
            name="activity_type",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
    )
    kind: Mapped[PathItemKind] = mapped_column(
        Enum(
            PathItemKind,
            name="path_item_kind",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
    )
    pack_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("packs.id", ondelete="CASCADE"),
        nullable=False,
    )
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    pack: Mapped[Pack] = relationship()
    completions: Mapped[list[ActivityCompletion]] = relationship(
        back_populates="path_item"
    )
