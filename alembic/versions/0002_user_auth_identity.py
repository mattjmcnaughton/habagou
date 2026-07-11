"""Add authenticated identity columns to users.

Revision ID: 0002_user_auth_identity
Revises: 0001_initial_schema
Create Date: 2026-07-05
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0002_user_auth_identity"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("auth_issuer", sa.String(), nullable=True))
    op.add_column("users", sa.Column("auth_subject", sa.String(), nullable=True))
    op.add_column("users", sa.Column("email", sa.String(), nullable=True))
    op.create_index(
        "ix_users_auth_identity",
        "users",
        ["auth_issuer", "auth_subject"],
        unique=True,
        postgresql_where=sa.text(
            "auth_issuer IS NOT NULL AND auth_subject IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_users_auth_identity", table_name="users")
    op.drop_column("users", "email")
    op.drop_column("users", "auth_subject")
    op.drop_column("users", "auth_issuer")
