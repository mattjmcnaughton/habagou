"""Learner account ORM model."""

from __future__ import annotations

import uuid
from datetime import (
    datetime,  # noqa: TC003 - SQLAlchemy resolves mapped annotations at runtime.
)
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Index, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from habagou.db import Base

if TYPE_CHECKING:
    from habagou.models.progress import ActivityCompletion


class User(Base):
    """Learner account.

    Progress is user-scoped and the current user is resolved from auth session
    state at the API boundary.
    """

    __tablename__ = "users"
    __table_args__ = (
        Index(
            "ix_users_auth_identity",
            "auth_issuer",
            "auth_subject",
            unique=True,
            postgresql_where=text(
                "auth_issuer IS NOT NULL AND auth_subject IS NOT NULL"
            ),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    is_guest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auth_issuer: Mapped[str | None] = mapped_column(String, nullable=True)
    auth_subject: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    completions: Mapped[list[ActivityCompletion]] = relationship(back_populates="user")
