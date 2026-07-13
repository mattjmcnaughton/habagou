"""Migration 0006 demotes ``packs.slug`` to a nullable seed key.

Upgrade makes the column nullable and swaps the plain ``UNIQUE(slug)`` for a
partial unique index (``WHERE slug IS NOT NULL``): duplicate NULL slugs are
allowed (many user packs), duplicate non-null slugs stay rejected. Downgrade
restores NOT NULL and the unnamed unique constraint, and assumes no NULL slugs
remain.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING

import asyncpg

from tests.integration.conftest import (
    _create_database,
    _drop_database,
    _render_url,
    _with_database,
)
from tests.integration.test_pack_owner_migration import (
    _connect,
    _downgrade_migration,
    _run_migration,
)

if TYPE_CHECKING:
    from sqlalchemy.engine import URL

REV_0005 = "0005_drop_pack_status"
REV_0006 = "0006_nullable_pack_slug"


async def _insert_pack(url: URL, slug: str | None) -> None:
    connection = await _connect(url)
    try:
        await connection.execute(
            "INSERT INTO packs "
            "(id, slug, title, glyph, color, sort_order, created_at, updated_at) "
            "VALUES ($1, $2, 'T', 'x', '#000000', 1, now(), now())",
            uuid.uuid4(),
            slug,
        )
    finally:
        await connection.close()


async def _slug_is_nullable(url: URL) -> bool:
    connection = await _connect(url)
    try:
        result = await connection.fetchval(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name = 'packs' AND column_name = 'slug'"
        )
        return result == "YES"
    finally:
        await connection.close()


async def _delete_null_slug_packs(url: URL) -> None:
    connection = await _connect(url)
    try:
        await connection.execute("DELETE FROM packs WHERE slug IS NULL")
    finally:
        await connection.close()


def test_migration_makes_slug_nullable_with_partial_unique_index(
    base_database_url: URL,
) -> None:
    database_name = f"habagou_migration_{uuid.uuid4().hex}"
    test_url = _with_database(base_database_url, database_name)
    rendered = _render_url(test_url)
    try:
        asyncio.run(_create_database(test_url))

        # At 0005 slug is still NOT NULL.
        _run_migration(rendered, REV_0005)
        assert not asyncio.run(_slug_is_nullable(test_url))

        # 0006 makes it nullable.
        _run_migration(rendered, REV_0006)
        assert asyncio.run(_slug_is_nullable(test_url))

        # Duplicate NULL slugs are allowed (many user packs).
        asyncio.run(_insert_pack(test_url, None))
        asyncio.run(_insert_pack(test_url, None))

        # A non-null slug persists, and a duplicate of it is still rejected.
        asyncio.run(_insert_pack(test_url, "dup"))
        try:
            asyncio.run(_insert_pack(test_url, "dup"))
            raise AssertionError("duplicate non-null slug should be rejected")
        except asyncpg.exceptions.UniqueViolationError:
            pass

        # Downgrade assumes no NULL slugs: clear them, then restore NOT NULL.
        asyncio.run(_delete_null_slug_packs(test_url))
        _downgrade_migration(rendered, REV_0005)
        assert not asyncio.run(_slug_is_nullable(test_url))

        # NOT NULL is enforced again: a NULL slug insert now fails.
        try:
            asyncio.run(_insert_pack(test_url, None))
            raise AssertionError("NULL slug should be rejected after downgrade")
        except asyncpg.exceptions.NotNullViolationError:
            pass
    finally:
        asyncio.run(_drop_database(test_url))
