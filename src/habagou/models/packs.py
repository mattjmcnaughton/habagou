"""Pack ORM models: the pack and its character and sentence members."""

from __future__ import annotations

import uuid
from datetime import (
    datetime,  # noqa: TC003 - SQLAlchemy resolves mapped annotations at runtime.
)
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
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


class Category(Base):
    """Library category grouping curated packs.

    Seeded from ``data/packs/categories.json``; user packs carry no category.
    """

    __tablename__ = "categories"

    slug: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)

    packs: Mapped[list[Pack]] = relationship(back_populates="category")


class Pack(Base):
    """Character pack.

    Two-tier ownership: ``owner_id IS NULL`` marks a global, curated pack
    (seeded and visible to everyone); a non-null ``owner_id`` marks a private
    pack owned by a single user.
    """

    __tablename__ = "packs"
    __table_args__ = (
        Index("ix_packs_owner", "owner_id"),
        Index("ix_packs_category", "category_slug"),
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
    # Catalog metadata for the pack library. Curated packs carry a category
    # and description; user packs persist NULL for both. ``starter`` marks
    # packs enabled by default for every user (the lazy enablement overlay in
    # user_pack_settings only stores explicit overrides of this default).
    category_slug: Mapped[str | None] = mapped_column(
        String,
        # RESTRICT: deleting a category that still has packs is a seed-pipeline
        # bug and must fail loudly.
        ForeignKey("categories.slug", ondelete="RESTRICT"),
        nullable=True,
    )
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    starter: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
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
    category: Mapped[Category | None] = relationship(back_populates="packs")


class UserPackSetting(Base):
    """Per-user enablement override for a global pack.

    Lazy overlay: *absence of a row means "use the pack's default"*, which is
    ``packs.starter`` — so starter packs are enabled for every user (existing,
    new, and guest) without any per-user writes. A row only records an explicit
    override: disabling a starter pack (``enabled=false``) or enabling a
    non-starter library pack (``enabled=true``). Owned packs are always
    enabled and never have rows.
    """

    __tablename__ = "user_pack_settings"

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
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


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
