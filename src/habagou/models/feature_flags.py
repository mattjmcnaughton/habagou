"""Per-user feature-flag override ORM model."""

from __future__ import annotations

import uuid  # noqa: TC003 - SQLAlchemy resolves mapped annotations at runtime.
from datetime import (
    datetime,  # noqa: TC003 - SQLAlchemy resolves mapped annotations at runtime.
)

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from habagou.db import Base


class UserFeatureOverride(Base):
    """A per-user exception to a feature flag's default.

    Flags themselves are defined in code (``habagou.services.feature_flags``);
    only the exceptions live in the database. A missing row means "use the
    default", and rows for flags that no longer exist in code are ignored at
    resolution time, so deleting a flag never requires a data migration.
    """

    __tablename__ = "user_feature_overrides"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    flag_key: Mapped[str] = mapped_column(String, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
