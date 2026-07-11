from __future__ import annotations

import pytest

from habagou.auth import AuthIdentity, fetch_identity
from habagou.services.auth import _normalize_username


def test_keycloak_identity_uses_oidc_claims() -> None:
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


def test_keycloak_identity_requires_stable_claims() -> None:
    with pytest.raises(ValueError, match="required identity claims"):
        fetch_identity({"userinfo": {"preferred_username": "dev"}})


def test_normalize_username() -> None:
    assert _normalize_username(" Dev User ") == "dev-user"
    assert _normalize_username(" ") == "user"
