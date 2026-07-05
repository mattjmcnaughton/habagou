"""SQLAlchemy ORM models."""

from __future__ import annotations

import uuid
from datetime import (
    datetime,  # noqa: TC003 - SQLAlchemy resolves mapped annotations at runtime.
)
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from habagou.db import Base

GUEST_USER_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")


class PackStatus(StrEnum):
    """Lifecycle status for a pack."""

    DRAFT = "draft"
    PUBLISHED = "published"
    RETIRED = "retired"


class ActivityType(StrEnum):
    """Activity variants that can create completion events."""

    TRACE = "trace"
    MATCH = "match"
    SENTENCE = "sentence"


class User(Base):
    """Learner account.

    v1 creates a single well-known guest user, but progress is user-scoped from
    day one so authentication can replace the resolver later.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    is_guest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    completions: Mapped[list[ActivityCompletion]] = relationship(back_populates="user")


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


class Pack(Base):
    """Curated character pack."""

    __tablename__ = "packs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    glyph: Mapped[str] = mapped_column(String, nullable=False)
    color: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[PackStatus] = mapped_column(
        Enum(
            PackStatus,
            name="pack_status",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
        default=PackStatus.DRAFT,
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    characters: Mapped[list[PackCharacter]] = relationship(
        back_populates="pack",
        cascade="all, delete-orphan",
        order_by="PackCharacter.position",
    )
    sentences: Mapped[list[PackSentence]] = relationship(
        back_populates="pack",
        cascade="all, delete-orphan",
        order_by="PackSentence.position",
    )
    completions: Mapped[list[ActivityCompletion]] = relationship(back_populates="pack")


class PackCharacter(Base):
    """Contextual character metadata for a pack."""

    __tablename__ = "pack_characters"
    __table_args__ = (
        UniqueConstraint(
            "pack_id",
            "position",
            name="uq_pack_characters_pack_position",
        ),
    )

    pack_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("packs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    pinyin: Mapped[str] = mapped_column(String, nullable=False)
    meaning: Mapped[str] = mapped_column(String, nullable=False)

    pack: Mapped[Pack] = relationship(back_populates="characters")
    character: Mapped[Character] = relationship(back_populates="pack_links")


class PackSentence(Base):
    """Sentence shown in the sentence tracing activity."""

    __tablename__ = "pack_sentences"
    __table_args__ = (
        UniqueConstraint(
            "pack_id",
            "position",
            name="uq_pack_sentences_pack_position",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pack_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("packs.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    hanzi: Mapped[str] = mapped_column(String, nullable=False)
    pinyin: Mapped[str] = mapped_column(String, nullable=False)
    translation: Mapped[str] = mapped_column(String, nullable=False)

    pack: Mapped[Pack] = relationship(back_populates="sentences")


class ActivityCompletion(Base):
    """Append-only activity completion event."""

    __tablename__ = "activity_completions"
    __table_args__ = (Index("ix_activity_completions_user_pack", "user_id", "pack_id"),)

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
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="completions")
    pack: Mapped[Pack] = relationship(back_populates="completions")


__all__ = [
    "ActivityCompletion",
    "ActivityType",
    "Character",
    "GUEST_USER_ID",
    "Pack",
    "PackCharacter",
    "PackSentence",
    "PackStatus",
    "User",
]
