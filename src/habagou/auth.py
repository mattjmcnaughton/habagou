"""Configurable OIDC provider registration and identity extraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from authlib.integrations.starlette_client import OAuth

if TYPE_CHECKING:
    from habagou.config import Settings

oauth = OAuth()


@dataclass(frozen=True)
class AuthIdentity:
    issuer: str
    subject: str
    username: str
    display_name: str
    email: str | None = None


def register_provider(settings: Settings) -> None:
    """Register the configured OIDC provider through discovery metadata."""
    metadata_url = settings.oidc_metadata_url or (
        f"{settings.oidc_issuer.rstrip('/')}/.well-known/openid-configuration"
    )
    oauth.register(
        name=settings.oidc_provider,
        server_metadata_url=metadata_url,
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
        client_kwargs={"scope": settings.oidc_scopes},
    )


def fetch_identity(token: dict[str, Any]) -> AuthIdentity:
    """Map standard OIDC claims to the app's stable identity shape."""
    return _oidc_identity(token)


def _oidc_identity(token: dict[str, Any]) -> AuthIdentity:
    claims = token.get("userinfo") or token.get("id_token") or {}
    issuer = str(claims.get("iss") or "")
    subject = str(claims.get("sub") or "")
    username = str(claims.get("preferred_username") or claims.get("email") or subject)
    display_name = str(claims.get("name") or username)
    email = claims.get("email")
    # An email the provider itself marks unverified must never become identity
    # data: admin classification (habagou.authz) derives from the email domain,
    # so trusting it would let a self-signup mint an admin address. An absent
    # claim keeps the email (matching providers that omit the flag entirely).
    if claims.get("email_verified") is False:
        email = None

    if not issuer or not subject or not username:
        raise ValueError("OIDC token is missing required identity claims")

    return AuthIdentity(
        issuer=issuer,
        subject=subject,
        username=username,
        display_name=display_name,
        email=str(email) if email else None,
    )
