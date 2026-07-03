"""Initial application schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-07-03
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

pack_status = postgresql.ENUM(
    "draft",
    "published",
    "retired",
    name="pack_status",
    create_type=False,
)
activity_type = postgresql.ENUM(
    "trace",
    "match",
    "sentence",
    name="activity_type",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    pack_status.create(bind, checkfirst=True)
    activity_type.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("is_guest", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_table(
        "characters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("hanzi", sa.String(), nullable=False),
        sa.Column(
            "stroke_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("stroke_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hanzi"),
    )
    op.create_table(
        "packs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("glyph", sa.String(), nullable=False),
        sa.Column("color", sa.String(), nullable=False),
        sa.Column("status", pack_status, nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "pack_characters",
        sa.Column("pack_id", sa.Uuid(), nullable=False),
        sa.Column("character_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("pinyin", sa.String(), nullable=False),
        sa.Column("meaning", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["character_id"], ["characters.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["pack_id"], ["packs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("pack_id", "character_id"),
        sa.UniqueConstraint(
            "pack_id",
            "position",
            name="uq_pack_characters_pack_position",
        ),
    )
    op.create_table(
        "pack_sentences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pack_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("hanzi", sa.String(), nullable=False),
        sa.Column("pinyin", sa.String(), nullable=False),
        sa.Column("translation", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["pack_id"], ["packs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "pack_id",
            "position",
            name="uq_pack_sentences_pack_position",
        ),
    )
    op.create_table(
        "activity_completions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("pack_id", sa.Uuid(), nullable=False),
        sa.Column("activity", activity_type, nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["pack_id"], ["packs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_activity_completions_user_pack",
        "activity_completions",
        ["user_id", "pack_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_activity_completions_user_pack", table_name="activity_completions"
    )
    op.drop_table("activity_completions")
    op.drop_table("pack_sentences")
    op.drop_table("pack_characters")
    op.drop_table("packs")
    op.drop_table("characters")
    op.drop_table("users")

    bind = op.get_bind()
    activity_type.drop(bind, checkfirst=True)
    pack_status.drop(bind, checkfirst=True)
