from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import asyncpg
import pytest
from alembic.config import Config
from sqlalchemy.engine import URL, make_url

from alembic import command
from habagou import db
from habagou.config import settings
from scripts.import_stroke_data import archive_path, import_corpus
from scripts.seed import seed_database

TEMPLATE_PREFIX = "habagou_test_base"
RUN_ID = uuid.uuid4().hex[:12]

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
def worker_id() -> str:
    return os.environ.get("PYTEST_XDIST_WORKER", "gw0")


@pytest.fixture(scope="session")
def base_database_url(worker_id: str) -> URL:
    url = make_url(settings.database_url)
    return _with_database(url, f"{TEMPLATE_PREFIX}_{RUN_ID}_{worker_id}")


@pytest.fixture(scope="session", autouse=True)
def template_database(base_database_url: URL) -> Generator[None]:
    _create_template_database(base_database_url)
    try:
        yield
    finally:
        asyncio.run(db.dispose_engine())
        asyncio.run(_drop_database(base_database_url))


@pytest.fixture(autouse=True)
def isolated_database(
    base_database_url: URL, request: pytest.FixtureRequest
) -> Generator[None]:
    database_name = f"habagou_test_{uuid.uuid4().hex}"
    test_url = _with_database(base_database_url, database_name)
    template_name = _database_name(base_database_url)
    created = False
    try:
        asyncio.run(_create_database_from_template(test_url, template_name))
        created = True
        asyncio.run(db.configure_database_url(_render_url(test_url)))
        request.node.user_properties.append(("database", database_name))

        yield
    finally:
        asyncio.run(db.dispose_engine())
        if created:
            asyncio.run(_drop_database(test_url))


def _create_template_database(template_url: URL) -> None:
    asyncio.run(_drop_database(template_url))
    created = False
    try:
        asyncio.run(_create_database(template_url))
        created = True
        _run_migrations(_render_url(template_url))
        asyncio.run(_import_and_seed_template_database(template_url))
    except Exception:
        asyncio.run(db.dispose_engine())
        if created:
            asyncio.run(_drop_database(template_url))
        raise
    else:
        asyncio.run(db.dispose_engine())


async def _import_and_seed_template_database(template_url: URL) -> None:
    await db.configure_database_url(_render_url(template_url))
    await import_corpus(
        archive=archive_path(),
        subset_path=Path("tests/fixtures/stroke_subset.txt"),
    )
    await seed_database()


async def _create_database(database_url: URL) -> None:
    connection = await _connect_admin(database_url)
    try:
        await connection.execute(
            f'CREATE DATABASE "{database_url.database}" TEMPLATE template0'
        )
    finally:
        await connection.close()


async def _create_database_from_template(database_url: URL, template_name: str) -> None:
    connection = await _connect_admin(database_url)
    try:
        await connection.execute(
            f'CREATE DATABASE "{database_url.database}" TEMPLATE "{template_name}"'
        )
    finally:
        await connection.close()


async def _drop_database(database_url: URL) -> None:
    if database_url.database is None:
        raise RuntimeError("database URL must include a database name")

    connection = await _connect_admin(database_url)
    try:
        await connection.execute(
            """
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = $1 AND pid <> pg_backend_pid()
            """,
            database_url.database,
        )
        await connection.execute(f'DROP DATABASE IF EXISTS "{database_url.database}"')
    finally:
        await connection.close()


async def _connect_admin(database_url: URL) -> asyncpg.Connection:
    admin_url = _with_database(database_url, "postgres")
    return await asyncpg.connect(
        user=admin_url.username,
        password=admin_url.password,
        database=admin_url.database,
        host=admin_url.query.get("host") or admin_url.host,
        port=admin_url.port,
    )


def _run_migrations(database_url: str) -> None:
    previous_env_url = os.environ.get("DATABASE_URL")
    previous_settings_url = settings.database_url
    os.environ["DATABASE_URL"] = database_url
    settings.database_url = database_url
    try:
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        settings.database_url = previous_settings_url
        if previous_env_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_env_url


def _with_database(url: URL, database: str) -> URL:
    return url.set(database=database)


def _database_name(url: URL) -> str:
    if url.database is None:
        raise RuntimeError("database URL must include a database name")
    return url.database


def _render_url(url: URL) -> str:
    return url.render_as_string(hide_password=False)
