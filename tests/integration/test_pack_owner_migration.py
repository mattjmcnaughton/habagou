"""Migration 0004 adds ``packs.owner_id`` (NULL = global, non-null = private).

Existing pack rows (seeded/curated) must backfill ``owner_id IS NULL`` and a
clean downgrade must remove the column.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import TYPE_CHECKING

import asyncpg
from alembic.config import Config

from alembic import command
from habagou.config import settings
from tests.integration.conftest import (
    _create_database,
    _drop_database,
    _render_url,
    _with_database,
)

if TYPE_CHECKING:
    from sqlalchemy.engine import URL

REV_0003 = "0003_learning_path_schema"
REV_0004 = "0004_pack_owner_id"


def _run_migration(database_url: str, revision: str) -> None:
    previous_env_url = os.environ.get("DATABASE_URL")
    previous_settings_url = settings.database_url
    os.environ["DATABASE_URL"] = database_url
    settings.database_url = database_url
    try:
        command.upgrade(Config("alembic.ini"), revision)
    finally:
        settings.database_url = previous_settings_url
        if previous_env_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_env_url


def _downgrade_migration(database_url: str, revision: str) -> None:
    previous_env_url = os.environ.get("DATABASE_URL")
    previous_settings_url = settings.database_url
    os.environ["DATABASE_URL"] = database_url
    settings.database_url = database_url
    try:
        command.downgrade(Config("alembic.ini"), revision)
    finally:
        settings.database_url = previous_settings_url
        if previous_env_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_env_url


async def _connect(url: URL) -> asyncpg.Connection:
    return await asyncpg.connect(
        user=url.username,
        password=url.password,
        database=url.database,
        host=url.query.get("host") or url.host,
        port=url.port,
    )


async def _insert_legacy_pack(url: URL) -> None:
    connection = await _connect(url)
    try:
        await connection.execute(
            "INSERT INTO packs "
            "(id, slug, title, glyph, color, status, sort_order, "
            "created_at, updated_at) "
            "VALUES ($1, 'legacy', 'Legacy', 'x', '#000000', 'published', 1, "
            "now(), now())",
            uuid.uuid4(),
        )
    finally:
        await connection.close()


async def _fetch_owner_ids(url: URL) -> list[uuid.UUID | None]:
    connection = await _connect(url)
    try:
        rows = await connection.fetch("SELECT owner_id FROM packs")
        return [row["owner_id"] for row in rows]
    finally:
        await connection.close()


async def _column_exists(url: URL, table: str, column: str) -> bool:
    connection = await _connect(url)
    try:
        result = await connection.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_name = $1 AND column_name = $2)",
            table,
            column,
        )
        return bool(result)
    finally:
        await connection.close()


async def _fetch_row_count(url: URL, table: str) -> int:
    connection = await _connect(url)
    try:
        result = await connection.fetchval(f"SELECT count(*) FROM {table}")
        return int(result)
    finally:
        await connection.close()


def test_migration_backfills_existing_packs_with_null_owner(
    base_database_url: URL,
) -> None:
    database_name = f"habagou_migration_{uuid.uuid4().hex}"
    test_url = _with_database(base_database_url, database_name)
    rendered = _render_url(test_url)
    try:
        asyncio.run(_create_database(test_url))

        # Bring the DB to the pre-ownership revision and seed a pack.
        _run_migration(rendered, REV_0003)
        asyncio.run(_insert_legacy_pack(test_url))
        assert not asyncio.run(_column_exists(test_url, "packs", "owner_id"))

        # The ownership migration must apply cleanly and backfill NULL.
        _run_migration(rendered, REV_0004)
        assert asyncio.run(_fetch_owner_ids(test_url)) == [None]

        # Downgrade removes the added column and leaves the row intact.
        _downgrade_migration(rendered, REV_0003)
        assert not asyncio.run(_column_exists(test_url, "packs", "owner_id"))
        remaining = asyncio.run(_fetch_row_count(test_url, "packs"))
        assert remaining == 1
    finally:
        asyncio.run(_drop_database(test_url))
