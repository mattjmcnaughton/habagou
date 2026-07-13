"""Demote ``packs.slug`` to a nullable seed key.

Slug is now a seed-only identifier: curated (seeded) packs keep a stable,
non-null slug used by the idempotent seed upsert, while user-created packs
persist ``slug IS NULL``. Packs are addressed by ``id`` everywhere on the API
surface, so slug no longer needs to be present or globally unique.

Upgrade drops the plain ``UNIQUE(slug)`` constraint from 0001
(``packs_slug_key``) and makes the column nullable, replacing uniqueness with a
partial unique index (``ix_packs_slug``, ``WHERE slug IS NOT NULL``): duplicate
NULLs are allowed (many user packs), duplicate non-null slugs are still
rejected (seed keys stay unique).

Downgrade restores the original schema: the partial index is dropped, the
column is made NOT NULL again, and the unnamed ``UNIQUE(slug)`` constraint is
recreated. Downgrade assumes no NULL slugs remain (true when only seeded packs
exist); if user packs with NULL slug are present the NOT NULL restore will fail
by design, since 0001 had no way to represent them.

Revision ID: 0006_nullable_pack_slug
Revises: 0005_drop_pack_status
Create Date: 2026-07-13
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0006_nullable_pack_slug"
down_revision: str | None = "0005_drop_pack_status"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.drop_constraint("packs_slug_key", "packs", type_="unique")
    op.alter_column("packs", "slug", existing_type=sa.String(), nullable=True)
    op.create_index(
        "ix_packs_slug",
        "packs",
        ["slug"],
        unique=True,
        postgresql_where=sa.text("slug IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_packs_slug", table_name="packs")
    # Assumes no NULL slugs remain (only seeded packs exist); NOT NULL restore
    # fails by design otherwise.
    op.alter_column("packs", "slug", existing_type=sa.String(), nullable=False)
    op.create_unique_constraint("packs_slug_key", "packs", ["slug"])
