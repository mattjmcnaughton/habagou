"""Drop ``packs.status`` and the ``pack_status`` enum.

Pack visibility moved from ``PackStatus`` to ownership (``owner_id``): global
packs (``owner_id IS NULL``) are the exact successor of the old published
packs, so the status column and its Postgres enum type are now unused.

Downgrade recreates the enum and column, backfilling every existing row to
``'published'`` -- all surviving packs are global/curated, the successor of
what "published" meant.

Revision ID: 0005_drop_pack_status
Revises: 0004_pack_owner_id
Create Date: 2026-07-13
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005_drop_pack_status"
down_revision: str | None = "0004_pack_owner_id"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

pack_status = postgresql.ENUM(
    "draft",
    "published",
    "retired",
    name="pack_status",
    create_type=False,
)


def upgrade() -> None:
    # Drop the column first so the enum type has no dependents left to remove.
    op.drop_column("packs", "status")
    pack_status.drop(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    pack_status.create(op.get_bind(), checkfirst=True)
    # server_default backfills existing rows to 'published'; drop it afterwards
    # to match the original schema (0001 created the column without a default).
    op.add_column(
        "packs",
        sa.Column("status", pack_status, nullable=False, server_default="published"),
    )
    op.alter_column("packs", "status", server_default=None)
