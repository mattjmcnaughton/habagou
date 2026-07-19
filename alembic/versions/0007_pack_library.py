"""Pack library: categories, catalog columns, per-user enablement overlay.

Introduces the browsable pack library (docs/plans/pack-library.md):

- ``categories``: ordered library categories, seeded from
  ``data/packs/categories.json``.
- ``packs`` gains catalog metadata: ``category_slug`` (nullable FK, NULL for
  user packs; RESTRICT so deleting a category with packs fails loudly),
  ``description`` (nullable), and ``starter`` (server default false).
- ``user_pack_settings``: lazy per-user enablement overlay. Absence of a row
  means "use the pack's default" (``packs.starter``), so starter packs are
  enabled for every user with no per-user writes; rows only record explicit
  overrides.

No data backfill here: catalog values (including ``starter=true`` for the
existing curated packs) arrive via the seed pipeline, which runs in the same
bootstrap pass as migrations.

Downgrade drops the new tables and columns; explicit enablement choices are
lost by design.

Revision ID: 0007_pack_library
Revises: 0006_nullable_pack_slug
Create Date: 2026-07-19
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0007_pack_library"
down_revision: str | None = "0006_nullable_pack_slug"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("slug", sa.String(), primary_key=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
    )

    op.add_column(
        "packs",
        sa.Column(
            "category_slug",
            sa.String(),
            sa.ForeignKey(
                "categories.slug",
                ondelete="RESTRICT",
                name="packs_category_slug_fkey",
            ),
            nullable=True,
        ),
    )
    op.add_column("packs", sa.Column("description", sa.String(), nullable=True))
    op.add_column(
        "packs",
        sa.Column(
            "starter",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_index("ix_packs_category", "packs", ["category_slug"])

    op.create_table(
        "user_pack_settings",
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "pack_id",
            sa.Uuid(),
            sa.ForeignKey("packs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("user_pack_settings")
    op.drop_index("ix_packs_category", table_name="packs")
    op.drop_column("packs", "starter")
    op.drop_column("packs", "description")
    op.drop_column("packs", "category_slug")
    op.drop_table("categories")
