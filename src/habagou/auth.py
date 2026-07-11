"""OAuth/OIDC provider configuration and identity extraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from authlib.integrations.starlette_client import OAuth

if TYPE_CHECKING:
    from habagou.config import Settings

oauth = OAuth()
PROVIDER_NAME = "keycloak"


@dataclass(frozen=True)
class AuthIdentity:
    issuer: str
    subject: str
    username: str
    display_name: str
    email: str | None = None


def register_provider(settings: Settings) -> None:
    """Register Habagou's Keycloak OIDC provider."""
    metadata_url = settings.oidc_metadata_url or (
        f"{settings.oidc_issuer.rstrip('/')}/.well-known/openid-configuration"
    )
    oauth.register(
        name=PROVIDER_NAME,
        server_metadata_url=metadata_url,
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
        client_kwargs={"scope": "openid profile email"},
    )


def fetch_identity(token: dict[str, Any]) -> AuthIdentity:
    """Map a Keycloak OIDC token to the app's stable identity shape."""
    return _keycloak_identity(token)


def _keycloak_identity(token: dict[str, Any]) -> AuthIdentity:
    claims = token.get("userinfo") or token.get("id_token") or {}
    issuer = str(claims.get("iss") or "")
    subject = str(claims.get("sub") or "")
    username = str(claims.get("preferred_username") or claims.get("email") or subject)
    display_name = str(claims.get("name") or username)
    email = claims.get("email")

    if not issuer or not subject or not username:
        raise ValueError("OIDC token is missing required identity claims")

    return AuthIdentity(
        issuer=issuer,
        subject=subject,
        username=username,
        display_name=display_name,
        email=str(email) if email else None,
    )
