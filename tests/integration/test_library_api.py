"""Integration tests for the pack library and per-user enablement (WF-02)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from habagou import db
from habagou.app import create_app
from habagou.models import Pack, PathItem, User
from tests.integration.conftest import (
    auth_cookies,
    create_user,
    pack_id_by_slug,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@pytest.fixture
async def current_user() -> User:
    async with db.async_session() as session:
        user = await create_user(session)
        await session.commit()
        return user


@pytest.fixture
async def client(current_user: User) -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        client.cookies.update(auth_cookies(current_user.id))
        yield client


async def _add_library_pack(slug: str, *, starter: bool = False) -> uuid.UUID:
    """A curated (global) non-starter pack outside the seeded starter set."""
    async with db.async_session() as session:
        pack = Pack(
            slug=slug,
            title=f"Library {slug}",
            glyph="书",
            color="#3f8a86",
            category_slug="basics",
            description="A test library pack",
            starter=starter,
            sort_order=500,
        )
        session.add(pack)
        await session.commit()
        return pack.id


async def _bench_titles(client: AsyncClient) -> list[str]:
    response = await client.get("/api/v1/packs")
    assert response.status_code == 200
    return [pack["title"] for pack in response.json()]


@pytest.mark.workflow("WF-02")
@pytest.mark.anyio
async def test_library_lists_every_global_pack_grouped_and_flagged(
    client: AsyncClient,
) -> None:
    pack_id = await _add_library_pack("test-lib-pack")

    response = await client.get("/api/v1/library")

    assert response.status_code == 200
    categories = response.json()["categories"]
    assert [category["slug"] for category in categories] == [
        "basics",
        "numbers-time",
        "people-family",
        "food-drink",
        "places-travel",
        "daily-life",
        "nature-weather",
        "body-health",
        "school-work",
        "verbs-in-action",
    ]
    packs_by_id = {
        pack["id"]: pack for category in categories for pack in category["packs"]
    }
    greetings = packs_by_id[str(await pack_id_by_slug("greetings"))]
    assert greetings["starter"] is True
    assert greetings["enabled"] is True
    added = packs_by_id[str(pack_id)]
    assert added["starter"] is False
    assert added["enabled"] is False
    assert added["description"] == "A test library pack"
    assert added["char_count"] == 0


@pytest.mark.workflow("WF-02")
@pytest.mark.anyio
async def test_library_excludes_owned_packs(
    client: AsyncClient,
    current_user: User,
) -> None:
    async with db.async_session() as session:
        session.add(
            Pack(
                owner_id=current_user.id,
                title="My private pack",
                glyph="私",
                color="#5b5fa8",
                sort_order=1,
            )
        )
        await session.commit()

    response = await client.get("/api/v1/library")

    titles = [
        pack["title"]
        for category in response.json()["categories"]
        for pack in category["packs"]
    ]
    assert "My private pack" not in titles


@pytest.mark.workflow("WF-02")
@pytest.mark.anyio
async def test_enable_adds_pack_to_bench_and_disable_removes_it(
    client: AsyncClient,
) -> None:
    pack_id = await _add_library_pack("test-lib-toggle")
    assert "Library test-lib-toggle" not in await _bench_titles(client)

    enable = await client.put(
        f"/api/v1/packs/{pack_id}/enabled", json={"enabled": True}
    )
    assert enable.status_code == 204
    assert "Library test-lib-toggle" in await _bench_titles(client)

    disable = await client.put(
        f"/api/v1/packs/{pack_id}/enabled", json={"enabled": False}
    )
    assert disable.status_code == 204
    assert "Library test-lib-toggle" not in await _bench_titles(client)

    # Disabled packs stay viewable by direct link (library preview).
    detail = await client.get(f"/api/v1/packs/{pack_id}")
    assert detail.status_code == 200
    assert detail.json()["enabled"] is False


@pytest.mark.workflow("WF-02")
@pytest.mark.anyio
async def test_disabling_starter_pack_removes_it_from_bench(
    client: AsyncClient,
) -> None:
    greetings_id = await pack_id_by_slug("greetings")

    response = await client.put(
        f"/api/v1/packs/{greetings_id}/enabled", json={"enabled": False}
    )

    assert response.status_code == 204
    assert "Greetings" not in await _bench_titles(client)
    # Re-enable restores the starter default state.
    await client.put(f"/api/v1/packs/{greetings_id}/enabled", json={"enabled": True})
    assert "Greetings" in await _bench_titles(client)


@pytest.mark.workflow("WF-02")
@pytest.mark.anyio
async def test_enablement_is_scoped_per_user(client: AsyncClient) -> None:
    greetings_id = await pack_id_by_slug("greetings")
    await client.put(f"/api/v1/packs/{greetings_id}/enabled", json={"enabled": False})

    async with db.async_session() as session:
        other = await create_user(session, username="other-library-user", email=None)
        await session.commit()
        other_id = other.id

    transport = ASGITransport(app=create_app())
    async with AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as other_client:
        other_client.cookies.update(auth_cookies(other_id))
        assert "Greetings" in await _bench_titles(other_client)


@pytest.mark.workflow("WF-02")
@pytest.mark.anyio
async def test_enable_rejects_owned_and_unknown_packs(
    client: AsyncClient,
    current_user: User,
) -> None:
    async with db.async_session() as session:
        owned = Pack(
            owner_id=current_user.id,
            title="Owned toggle target",
            glyph="私",
            color="#5b5fa8",
            sort_order=1,
        )
        session.add(owned)
        await session.commit()
        owned_id = owned.id

    owned_response = await client.put(
        f"/api/v1/packs/{owned_id}/enabled", json={"enabled": False}
    )
    assert owned_response.status_code == 409

    unknown_response = await client.put(
        f"/api/v1/packs/{uuid.uuid4()}/enabled", json={"enabled": True}
    )
    assert unknown_response.status_code == 404


@pytest.mark.workflow("WF-14")
@pytest.mark.anyio
async def test_disable_prunes_pending_path_items_but_keeps_completed(
    client: AsyncClient,
    current_user: User,
) -> None:
    # Materialize the queue, then complete the first item.
    path_body = (await client.get("/api/v1/path")).json()
    first = path_body["items"][0]
    complete = await client.post(
        f"/api/v1/path/items/{first['id']}/complete", json={"duration_ms": 900}
    )
    assert complete.status_code == 201

    async def item_count(pack_id: uuid.UUID) -> int:
        async with db.async_session() as session:
            result = await session.execute(
                select(PathItem).where(
                    PathItem.user_id == current_user.id,
                    PathItem.pack_id == pack_id,
                )
            )
            return len(list(result.scalars()))

    greetings_id = await pack_id_by_slug("greetings")
    before = await item_count(greetings_id)
    assert before > 0

    response = await client.put(
        f"/api/v1/packs/{greetings_id}/enabled", json={"enabled": False}
    )
    assert response.status_code == 204

    # Only the completed item survives; pending greetings items are pruned.
    after = await item_count(greetings_id)
    assert after == 1

    # The queue regenerates from the remaining enabled packs only.
    regenerated = (await client.get("/api/v1/path?limit=50")).json()
    greetings_pending = [
        item
        for item in regenerated["items"]
        if item["pack"]["title"] == "Greetings" and item["state"] != "done"
    ]
    assert greetings_pending == []
