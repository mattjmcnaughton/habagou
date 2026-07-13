"""Migration 0005 drops ``packs.status`` and the ``pack_status`` enum.

Upgrade removes both the column and the Postgres enum type; downgrade recreates
them, backfilling every surviving row to ``'published'`` (all remaining packs
are global/curated, the successor of what "published" meant).
"""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING

from tests.integration.conftest import (
    _create_database,
    _drop_database,
    _render_url,
    _with_database,
)
from tests.integration.test_pack_owner_migration import (
    _column_exists,
    _connect,
    _downgrade_migration,
    _run_migration,
)

if TYPE_CHECKING:
    from sqlalchemy.engine import URL

REV_0004 = "0004_pack_owner_id"
REV_0005 = "0005_drop_pack_status"


async def _insert_pack_with_status(url: URL, status: str) -> None:
    connection = await _connect(url)
    try:
        await connection.execute(
            "INSERT INTO packs "
            "(id, slug, title, glyph, color, status, sort_order, "
            "created_at, updated_at) "
            "VALUES ($1, 'legacy', 'Legacy', 'x', '#000000', $2, 1, "
            "now(), now())",
            uuid.uuid4(),
            status,
        )
    finally:
        await connection.close()


async def _fetch_statuses(url: URL) -> list[str]:
    connection = await _connect(url)
    try:
        rows = await connection.fetch("SELECT status FROM packs")
        return [row["status"] for row in rows]
    finally:
        await connection.close()


async def _enum_exists(url: URL, name: str) -> bool:
    connection = await _connect(url)
    try:
        result = await connection.fetchval(
            "SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = $1)",
            name,
        )
        return bool(result)
    finally:
        await connection.close()


def test_migration_drops_status_and_recreates_on_downgrade(
    base_database_url: URL,
) -> None:
    database_name = f"habagou_migration_{uuid.uuid4().hex}"
    test_url = _with_database(base_database_url, database_name)
    rendered = _render_url(test_url)
    try:
        asyncio.run(_create_database(test_url))

        # At 0004 the status column and its enum type still exist.
        _run_migration(rendered, REV_0004)
        asyncio.run(_insert_pack_with_status(test_url, "published"))
        assert asyncio.run(_column_exists(test_url, "packs", "status"))
        assert asyncio.run(_enum_exists(test_url, "pack_status"))

        # The drop migration removes both cleanly, leaving the row intact.
        _run_migration(rendered, REV_0005)
        assert not asyncio.run(_column_exists(test_url, "packs", "status"))
        assert not asyncio.run(_enum_exists(test_url, "pack_status"))

        # Downgrade recreates the enum + column and backfills to 'published'.
        _downgrade_migration(rendered, REV_0004)
        assert asyncio.run(_column_exists(test_url, "packs", "status"))
        assert asyncio.run(_enum_exists(test_url, "pack_status"))
        assert asyncio.run(_fetch_statuses(test_url)) == ["published"]
    finally:
        asyncio.run(_drop_database(test_url))
