"""Hanzi stroke-corpus ORM model."""

from __future__ import annotations

from datetime import (
    datetime,  # noqa: TC003 - SQLAlchemy resolves mapped annotations at runtime.
)
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from habagou.db import Base

if TYPE_CHECKING:
    from habagou.models.packs import PackCharacter


class Character(Base):
    """Single Hanzi stroke-corpus row."""

    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hanzi: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    stroke_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    stroke_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    pack_links: Mapped[list[PackCharacter]] = relationship(
        back_populates="character",
        cascade="all, delete-orphan",
    )
