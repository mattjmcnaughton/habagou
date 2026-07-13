"""Pack ORM models: the pack and its character and sentence members."""

from __future__ import annotations

import uuid
from datetime import (
    datetime,  # noqa: TC003 - SQLAlchemy resolves mapped annotations at runtime.
)
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from habagou.db import Base

if TYPE_CHECKING:
    from habagou.models.characters import Character
    from habagou.models.progress import ActivityCompletion
    from habagou.models.users import User


class Pack(Base):
    """Character pack.

    Two-tier ownership: ``owner_id IS NULL`` marks a global, curated pack
    (seeded and visible to everyone); a non-null ``owner_id`` marks a private
    pack owned by a single user.
    """

    __tablename__ = "packs"
    __table_args__ = (
        Index("ix_packs_owner", "owner_id"),
        # Slug is a nullable seed key: curated packs carry a stable, unique
        # non-null slug; user packs persist NULL. A partial unique index keeps
        # seed slugs unique while allowing many NULLs (see migration 0006).
        Index(
            "ix_packs_slug",
            "slug",
            unique=True,
            postgresql_where=text("slug IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        # CASCADE: a deleted user's private packs must not linger. SET NULL
        # would silently promote them to global packs -- a privacy leak.
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    slug: Mapped[str | None] = mapped_column(String, nullable=True)
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
