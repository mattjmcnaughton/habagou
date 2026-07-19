"""Admin feature-flag API contract tests (real app, real database)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient

from habagou import db
from habagou.app import create_app
from tests.integration.conftest import auth_cookies, create_user

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

FLAGS_URL = "/api/v1/admin/feature-flags"
SESSION_URL = "/api/v1/auth/session"


@pytest.fixture(autouse=True)
def _registered_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    """Register test flags; the real registry is empty until the first flag."""
    monkeypatch.setattr(
        "habagou.services.feature_flags.FLAG_DEFAULTS",
        {"new_review_ui": False, "practice_v2": True},
    )


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture
async def user_id() -> uuid.UUID:
    async with db.async_session() as session:
        user = await create_user(session, username="flag-target")
        await session.commit()
        return user.id


@pytest.fixture
async def admin_id() -> uuid.UUID:
    async with db.async_session() as session:
        admin = await create_user(
            session, username="flag-admin", email="matt@mattjmcnaughton.com"
        )
        await session.commit()
        return admin.id


@pytest.mark.workflow("WF-ADMIN-FLAGS")
@pytest.mark.anyio
async def test_flag_endpoints_require_admin(
    client: AsyncClient, user_id: uuid.UUID
) -> None:
    target = f"{FLAGS_URL}/new_review_ui/users/{user_id}"
    assert (await client.get(FLAGS_URL)).status_code == 401

    client.cookies.update(auth_cookies(user_id))
    assert (await client.get(FLAGS_URL)).status_code == 403
    assert (await client.put(target, json={"enabled": True})).status_code == 403
    assert (await client.delete(target)).status_code == 403


@pytest.mark.workflow("WF-ADMIN-FLAGS")
@pytest.mark.anyio
async def test_admin_lists_registered_flags(
    client: AsyncClient, admin_id: uuid.UUID
) -> None:
    client.cookies.update(auth_cookies(admin_id))
    response = await client.get(FLAGS_URL)
    assert response.status_code == 200
    assert response.json() == {
        "flags": [
            {"key": "new_review_ui", "enabled_default": False, "override_count": 0},
            {"key": "practice_v2", "enabled_default": True, "override_count": 0},
        ]
    }


@pytest.mark.workflow("WF-ADMIN-FLAGS")
@pytest.mark.anyio
async def test_override_set_resolves_on_session_and_clears(
    client: AsyncClient, admin_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    admin_cookies = auth_cookies(admin_id)
    target_cookies = auth_cookies(user_id)
    target = f"{FLAGS_URL}/new_review_ui/users/{user_id}"

    client.cookies.update(target_cookies)
    session_body = (await client.get(SESSION_URL)).json()
    assert session_body["user"]["feature_flags"] == {
        "new_review_ui": False,
        "practice_v2": True,
    }

    client.cookies.update(admin_cookies)
    response = await client.put(target, json={"enabled": True})
    assert response.status_code == 200
    assert response.json() == {
        "flag_key": "new_review_ui",
        "user_id": str(user_id),
        "enabled": True,
    }
    listed = (await client.get(FLAGS_URL)).json()["flags"]
    assert {f["key"]: f["override_count"] for f in listed} == {
        "new_review_ui": 1,
        "practice_v2": 0,
    }
    # The admin's own flags are untouched — the override targets one user.
    admin_session = (await client.get(SESSION_URL)).json()
    assert admin_session["user"]["feature_flags"]["new_review_ui"] is False

    client.cookies.update(target_cookies)
    session_body = (await client.get(SESSION_URL)).json()
    assert session_body["user"]["feature_flags"]["new_review_ui"] is True

    client.cookies.update(admin_cookies)
    assert (await client.delete(target)).status_code == 204
    # Idempotent: clearing an already-absent override is still a 204.
    assert (await client.delete(target)).status_code == 204

    client.cookies.update(target_cookies)
    session_body = (await client.get(SESSION_URL)).json()
    assert session_body["user"]["feature_flags"]["new_review_ui"] is False


@pytest.mark.workflow("WF-ADMIN-FLAGS")
@pytest.mark.anyio
async def test_override_unknown_flag_or_user_is_404(
    client: AsyncClient, admin_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    client.cookies.update(auth_cookies(admin_id))

    unknown_flag = f"{FLAGS_URL}/not_a_flag/users/{user_id}"
    assert (await client.put(unknown_flag, json={"enabled": True})).status_code == 404
    assert (await client.delete(unknown_flag)).status_code == 404

    unknown_user = f"{FLAGS_URL}/new_review_ui/users/{uuid.uuid4()}"
    assert (await client.put(unknown_user, json={"enabled": True})).status_code == 404
