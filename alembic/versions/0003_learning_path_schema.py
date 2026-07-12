"""Learning path schema: path items, review states, completion source.

Revision ID: 0003_learning_path_schema
Revises: 0002_user_auth_identity
Create Date: 2026-07-12
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003_learning_path_schema"
down_revision: str | None = "0002_user_auth_identity"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

# The activity_type enum already exists (created in 0001) and is reused here.
activity_type = postgresql.ENUM(
    "trace",
    "match",
    "sentence",
    name="activity_type",
    create_type=False,
)
path_item_kind = postgresql.ENUM(
    "new",
    "review",
    name="path_item_kind",
    create_type=False,
)
review_unit_type = postgresql.ENUM(
    "character",
    "sentence",
    name="review_unit_type",
    create_type=False,
)
completion_source = postgresql.ENUM(
    "pack",
    "path",
    name="completion_source",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    path_item_kind.create(bind, checkfirst=True)
    review_unit_type.create(bind, checkfirst=True)
    completion_source.create(bind, checkfirst=True)

    op.create_table(
        "path_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("activity", activity_type, nullable=False),
        sa.Column("kind", path_item_kind, nullable=False),
        sa.Column("pack_id", sa.Uuid(), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["pack_id"], ["packs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "position",
            name="uq_path_items_user_position",
        ),
    )
    op.create_index("ix_path_items_user", "path_items", ["user_id", "position"])

    op.create_table(
        "review_states",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("pack_id", sa.Uuid(), nullable=False),
        sa.Column("unit_type", review_unit_type, nullable=False),
        sa.Column("unit_ref", sa.String(), nullable=False),
        sa.Column("activity", activity_type, nullable=False),
        sa.Column("reps", sa.Integer(), nullable=False),
        # Nullable: a unit is recorded at generation time with reps=0 and no
        # last_seen_at/due_at ("introduced, not yet practiced"); the ladder
        # populates both on first completion.
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["pack_id"], ["packs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint(
            "user_id",
            "pack_id",
            "unit_type",
            "unit_ref",
            "activity",
        ),
    )
    op.create_index(
        "ix_review_states_user_due",
        "review_states",
        ["user_id", "due_at"],
    )

    # Add source with a server default so existing rows backfill to 'pack',
    # then drop the default (the ORM sets it explicitly going forward).
    op.add_column(
        "activity_completions",
        sa.Column(
            "source",
            completion_source,
            nullable=False,
            server_default="pack",
        ),
    )
    op.alter_column("activity_completions", "source", server_default=None)
    op.add_column(
        "activity_completions",
        sa.Column("path_item_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_activity_completions_path_item",
        "activity_completions",
        "path_items",
        ["path_item_id"],
        ["id"],
        ondelete="CASCADE",
    )
    # Invariant: a source='path' completion must reference a path item.
    op.create_check_constraint(
        "ck_activity_completions_path_source",
        "activity_completions",
        "source <> 'path' OR path_item_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_activity_completions_path_source",
        "activity_completions",
        type_="check",
    )
    op.drop_constraint(
        "fk_activity_completions_path_item",
        "activity_completions",
        type_="foreignkey",
    )
    op.drop_column("activity_completions", "path_item_id")
    op.drop_column("activity_completions", "source")

    op.drop_index("ix_review_states_user_due", table_name="review_states")
    op.drop_table("review_states")
    op.drop_index("ix_path_items_user", table_name="path_items")
    op.drop_table("path_items")

    bind = op.get_bind()
    completion_source.drop(bind, checkfirst=True)
    review_unit_type.drop(bind, checkfirst=True)
    path_item_kind.drop(bind, checkfirst=True)
