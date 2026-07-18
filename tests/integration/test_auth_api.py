from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from habagou import db
from habagou.app import create_app
from habagou.auth import AuthIdentity
from habagou.models import User
from tests.integration.conftest import auth_cookies, create_user

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


class StubOAuthClient:
    async def authorize_access_token(self, _request):
        return {"access_token": "stub"}


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.workflow("WF-AUTH-SIGN-IN")
@pytest.mark.anyio
async def test_callback_provisions_once_and_reuses_identity(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = AuthIdentity(
        issuer="https://issuer.example.test",
        subject="subject-1",
        username="dev",
        display_name="Dev User",
        email="dev@example.com",
    )
    monkeypatch.setattr(
        "habagou.routers.auth.oauth.create_client",
        lambda _provider: StubOAuthClient(),
    )
    monkeypatch.setattr("habagou.routers.auth.fetch_identity", lambda *_args: identity)

    first_response = await client.get("/auth/callback", follow_redirects=False)
    second_response = await client.get("/auth/callback", follow_redirects=False)

    assert first_response.status_code == 303
    assert second_response.status_code == 303
    async with db.async_session() as session:
        count = await session.scalar(
            select(func.count(User.id)).where(
                User.auth_issuer == identity.issuer,
                User.auth_subject == identity.subject,
            )
        )
        user = await session.scalar(
            select(User).where(
                User.auth_issuer == identity.issuer,
                User.auth_subject == identity.subject,
            )
        )

    assert count == 1
    assert user is not None
    assert user.username == "dev"
    assert user.display_name == "Dev User"
    assert user.email == "dev@example.com"
    assert "session" in client.cookies


@pytest.mark.anyio
async def test_callback_redirects_only_for_expected_auth_errors(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "habagou.routers.auth.oauth.create_client",
        lambda _provider: StubOAuthClient(),
    )
    monkeypatch.setattr(
        "habagou.routers.auth.fetch_identity",
        lambda _token: (_ for _ in ()).throw(ValueError("missing claims")),
    )

    response = await client.get("/auth/callback", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login?error=auth_failed"


@pytest.mark.anyio
async def test_callback_does_not_hide_unexpected_errors(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "habagou.routers.auth.oauth.create_client",
        lambda _provider: StubOAuthClient(),
    )
    monkeypatch.setattr(
        "habagou.routers.auth.fetch_identity",
        lambda _token: (_ for _ in ()).throw(RuntimeError("database bug")),
    )

    with pytest.raises(RuntimeError, match="database bug"):
        await client.get("/auth/callback", follow_redirects=False)


@pytest.mark.workflow("WF-AUTH-SIGN-OUT")
@pytest.mark.anyio
async def test_logout_clears_session(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = AuthIdentity(
        issuer="https://issuer.example.test",
        subject="logout-subject",
        username="logout-user",
        display_name="Logout User",
    )
    monkeypatch.setattr(
        "habagou.routers.auth.oauth.create_client",
        lambda _provider: StubOAuthClient(),
    )
    monkeypatch.setattr("habagou.routers.auth.fetch_identity", lambda *_args: identity)
    sign_in_response = await client.get("/auth/callback", follow_redirects=False)
    assert sign_in_response.status_code == 303

    logout_response = await client.post("/auth/logout")
    packs_response = await client.get("/api/v1/packs")

    assert logout_response.status_code == 204
    assert packs_response.status_code == 401


@pytest.mark.anyio
async def test_session_probe_reports_authenticated_user(client: AsyncClient) -> None:
    async with db.async_session() as session:
        user = await create_user(session, username="session-user")
        await session.commit()
    client.cookies.update(auth_cookies(user.id))

    response = await client.get("/api/v1/auth/session")

    assert response.status_code == 200
    assert response.json() == {
        "authenticated": True,
        "provider": "keycloak",
        "user": {
            "id": str(user.id),
            "username": "session-user",
            "display_name": "Test User",
            "email": "test@example.com",
            "is_admin": False,
        },
    }


@pytest.mark.anyio
async def test_session_probe_reports_admin_for_admin_domain_email(
    client: AsyncClient,
) -> None:
    async with db.async_session() as session:
        user = await create_user(
            session, username="admin-user", email="matt@mattjmcnaughton.com"
        )
        await session.commit()
    client.cookies.update(auth_cookies(user.id))

    response = await client.get("/api/v1/auth/session")

    assert response.status_code == 200
    assert response.json()["user"]["is_admin"] is True
