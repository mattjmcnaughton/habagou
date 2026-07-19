from __future__ import annotations

import asyncio
import base64
import json
import os
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import asyncpg
import pytest
from alembic.config import Config
from itsdangerous import TimestampSigner
from sqlalchemy import select
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import selectinload

from alembic import command
from habagou import db
from habagou.config import settings
from habagou.models import Pack, PackCharacter, User
from habagou.repositories.characters import reset_all_hanzi_cache
from scripts.import_stroke_data import cached_archive, import_corpus
from scripts.seed import load_seed_packs, required_hanzi, seed_database

TEMPLATE_PREFIX = "habagou_test_base"
RUN_ID = uuid.uuid4().hex[:12]

if TYPE_CHECKING:
    from collections.abc import Generator

    from sqlalchemy.ext.asyncio import AsyncSession


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
def _reset_corpus_cache() -> None:
    """Clear the process-wide corpus cache so it never leaks across tests.

    ``CharacterRepository.all_hanzi`` memoizes the corpus at module scope; each
    test runs against its own fresh template database, so the cache must start
    empty to avoid one test's corpus bleeding into another's.
    """
    reset_all_hanzi_cache()


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
    # The fixture file carries characters tests reference directly; the seed
    # requirement set tracks data/packs automatically so the template always
    # covers every curated pack without hand-maintaining the fixture.
    await import_corpus(
        archive=cached_archive(),
        subset_path=Path("tests/fixtures/stroke_subset.txt"),
        subset=required_hanzi(load_seed_packs()),
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


async def create_user(
    session: AsyncSession,
    *,
    username: str = "test-user",
    display_name: str = "Test User",
    email: str | None = "test@example.com",
) -> User:
    user = User(
        username=username,
        display_name=display_name,
        is_guest=False,
        auth_issuer="https://issuer.example.test",
        auth_subject=uuid.uuid4().hex,
        email=email,
    )
    session.add(user)
    await session.flush()
    return user


async def pack_by_slug(session: AsyncSession, slug: str) -> Pack | None:
    """Fetch a seeded pack by its known slug (test setup only).

    Production code addresses packs by id; tests still need to translate the
    fixed seed slugs into pack rows (and their ids) for arrange/assert steps.
    """
    result = await session.execute(
        select(Pack)
        .where(Pack.slug == slug)
        .options(
            selectinload(Pack.characters).selectinload(PackCharacter.character),
            selectinload(Pack.sentences),
        )
    )
    return result.scalar_one_or_none()


async def pack_by_title(session: AsyncSession, title: str) -> Pack | None:
    """Fetch a seeded pack by its display title (test setup only).

    Companion to :func:`pack_by_slug` for callers that only have the title from
    a response DTO, which no longer carries slug.
    """
    result = await session.execute(
        select(Pack)
        .where(Pack.title == title)
        .options(
            selectinload(Pack.characters).selectinload(PackCharacter.character),
            selectinload(Pack.sentences),
        )
    )
    return result.scalar_one_or_none()


async def pack_id_by_slug(slug: str) -> uuid.UUID:
    """Resolve a seeded pack's id from its known slug (test setup only)."""
    async with db.async_session() as session:
        pack = await pack_by_slug(session, slug)
        assert pack is not None
        return pack.id


async def pack_id_by_title(title: str) -> uuid.UUID:
    """Resolve a seeded pack's id from its display title (test setup only).

    Slug is no longer on the API surface, so tests that only know a pack from a
    response DTO (which carries ``title`` but not ``slug``) translate the title
    back to a row id here.
    """
    async with db.async_session() as session:
        pack = await pack_by_title(session, title)
        assert pack is not None
        return pack.id


def auth_cookies(user_id: uuid.UUID, secret: str | None = None) -> dict[str, str]:
    payload = base64.b64encode(json.dumps({"user_id": str(user_id)}).encode("utf-8"))
    signer = TimestampSigner(str(secret or settings.session_secret_key))
    return {"session": signer.sign(payload).decode("utf-8")}
