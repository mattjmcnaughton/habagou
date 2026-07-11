from __future__ import annotations

import pytest

from habagou import auth
from habagou.auth import AuthIdentity, fetch_identity
from habagou.config import Settings
from habagou.services.auth import _normalize_username


def test_registers_auth0_through_oidc_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registered: dict[str, object] = {}
    monkeypatch.setattr(
        auth.oauth, "register", lambda **kwargs: registered.update(kwargs)
    )

    auth.register_provider(
        Settings(
            oidc_provider="auth0",
            oidc_issuer="https://tenant.auth0.com",
            oidc_client_id="client-id",
            oidc_client_secret="client-secret",
        )
    )

    assert registered == {
        "name": "auth0",
        "server_metadata_url": "https://tenant.auth0.com/.well-known/openid-configuration",
        "client_id": "client-id",
        "client_secret": "client-secret",
        "client_kwargs": {"scope": "openid profile email"},
    }


def test_oidc_identity_uses_standard_claims() -> None:
    identity = fetch_identity(
        {
            "userinfo": {
                "iss": "http://keycloak/realms/habagou",
                "sub": "subject-1",
                "preferred_username": "dev",
                "name": "Dev User",
                "email": "dev@example.com",
            }
        },
    )

    assert identity == AuthIdentity(
        issuer="http://keycloak/realms/habagou",
        subject="subject-1",
        username="dev",
        display_name="Dev User",
        email="dev@example.com",
    )


def test_oidc_identity_requires_stable_claims() -> None:
    with pytest.raises(ValueError, match="required identity claims"):
        fetch_identity({"userinfo": {"preferred_username": "dev"}})


def test_normalize_username() -> None:
    assert _normalize_username(" Dev User ") == "dev-user"
    assert _normalize_username(" ") == "user"
