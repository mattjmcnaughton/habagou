"""Authorization predicates over the resolved user.

Admin status is derived from the user's email domain rather than stored: the
email is refreshed from the identity provider on every sign-in
(:meth:`habagou.services.auth.AuthService.sign_in`), so classification
self-heals and needs no migration or management UI. The trust anchor is the
OIDC provider's ``email`` claim — acceptable for the configured first-party
providers (see ``docs/auth.md``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from habagou.config import settings

if TYPE_CHECKING:
    from habagou.models import User


def is_admin(user: User) -> bool:
    """Whether ``user`` belongs to the admin class.

    True iff the user is not a guest and their email's domain — the part after
    the final ``@``, compared case-insensitively and exactly (no subdomain or
    suffix matching) — is one of ``settings.admin_email_domain_set``.
    """
    if user.is_guest or not user.email or "@" not in user.email:
        return False
    domain = user.email.rsplit("@", 1)[1].lower()
    return domain in settings.admin_email_domain_set
