"""Migration 0003 must apply cleanly to a DB with existing completion rows.

Existing ``activity_completions`` rows (written before the Learning Path
feature) must backfill ``source='pack'``.
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

REV_0002 = "0002_user_auth_identity"
REV_0003 = "0003_learning_path_schema"


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


async def _insert_legacy_completion(url: URL) -> None:
    connection = await _connect(url)
    try:
        user_id = uuid.uuid4()
        pack_id = uuid.uuid4()
        await connection.execute(
            "INSERT INTO users (id, username, display_name, is_guest, created_at) "
            "VALUES ($1, $2, $3, false, now())",
            user_id,
            "legacy-user",
            "Legacy User",
        )
        await connection.execute(
            "INSERT INTO packs "
            "(id, slug, title, glyph, color, status, sort_order, "
            "created_at, updated_at) "
            "VALUES ($1, 'legacy', 'Legacy', 'x', '#000000', 'published', 1, "
            "now(), now())",
            pack_id,
        )
        await connection.execute(
            "INSERT INTO activity_completions "
            "(user_id, pack_id, activity, duration_ms, completed_at) "
            "VALUES ($1, $2, 'trace', 100, now())",
            user_id,
            pack_id,
        )
    finally:
        await connection.close()


async def _fetch_sources(url: URL) -> list[str]:
    connection = await _connect(url)
    try:
        rows = await connection.fetch("SELECT source FROM activity_completions")
        return [row["source"] for row in rows]
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


def test_migration_backfills_existing_completions_as_pack(
    base_database_url: URL,
) -> None:
    database_name = f"habagou_migration_{uuid.uuid4().hex}"
    test_url = _with_database(base_database_url, database_name)
    rendered = _render_url(test_url)
    try:
        asyncio.run(_create_database(test_url))

        # Bring the DB to the pre-Learning-Path revision and seed a completion.
        _run_migration(rendered, REV_0002)
        asyncio.run(_insert_legacy_completion(test_url))
        assert not asyncio.run(
            _column_exists(test_url, "activity_completions", "source")
        )

        # The Learning Path migration must apply cleanly and backfill 'pack'.
        _run_migration(rendered, REV_0003)
        assert asyncio.run(_fetch_sources(test_url)) == ["pack"]

        # Downgrade removes the added columns and leaves the row intact.
        _downgrade_migration(rendered, REV_0002)
        assert not asyncio.run(
            _column_exists(test_url, "activity_completions", "source")
        )
        remaining = asyncio.run(_fetch_row_count(test_url, "activity_completions"))
        assert remaining == 1
    finally:
        asyncio.run(_drop_database(test_url))


async def _fetch_row_count(url: URL, table: str) -> int:
    connection = await _connect(url)
    try:
        result = await connection.fetchval(f"SELECT count(*) FROM {table}")
        return int(result)
    finally:
        await connection.close()
