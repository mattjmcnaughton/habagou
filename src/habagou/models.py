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
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from habagou.db import Base


class ActivityType(StrEnum):
    """Activity variants that can create completion events."""

    TRACE = "trace"
    MATCH = "match"
    SENTENCE = "sentence"


class PathItemKind(StrEnum):
    """Whether a path item introduces new material or resurfaces due units."""

    NEW = "new"
    REVIEW = "review"


class ReviewUnitType(StrEnum):
    """The kind of reviewable unit tracked by a review state row."""

    CHARACTER = "character"
    SENTENCE = "sentence"


class CompletionSource(StrEnum):
    """Origin of a completion event: a whole-pack activity or a path item."""

    PACK = "pack"
    PATH = "path"


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
    """Character pack.

    Two-tier ownership: ``owner_id IS NULL`` marks a global, curated pack
    (seeded and visible to everyone); a non-null ``owner_id`` marks a private
    pack owned by a single user.
    """

    __tablename__ = "packs"
    __table_args__ = (Index("ix_packs_owner", "owner_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        # CASCADE: a deleted user's private packs must not linger. SET NULL
        # would silently promote them to global packs -- a privacy leak.
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    glyph: Mapped[str] = mapped_column(String, nullable=False)
    color: Mapped[str] = mapped_column(String, nullable=False)
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
    owner: Mapped[User | None] = relationship()


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


__all__ = [
    "ActivityCompletion",
    "ActivityType",
    "Character",
    "CompletionSource",
    "Pack",
    "PackCharacter",
    "PackSentence",
    "PathItem",
    "PathItemKind",
    "ReviewState",
    "ReviewUnitType",
    "User",
]
