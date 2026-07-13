"""Pack ownership: add ``packs.owner_id``.

Two-tier ownership: ``owner_id IS NULL`` marks a global, curated pack; a
non-null ``owner_id`` marks a private pack owned by a single user. Existing
rows backfill NULL automatically (nullable column). ``ondelete=CASCADE``
ensures a deleted user's private packs are removed rather than silently
promoted to global.

Revision ID: 0004_pack_owner_id
Revises: 0003_learning_path_schema
Create Date: 2026-07-13
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0004_pack_owner_id"
down_revision: str | None = "0003_learning_path_schema"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column(
        "packs",
        sa.Column("owner_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_packs_owner",
        "packs",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_packs_owner", "packs", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_packs_owner", table_name="packs")
    op.drop_constraint("fk_packs_owner", "packs", type_="foreignkey")
    op.drop_column("packs", "owner_id")
