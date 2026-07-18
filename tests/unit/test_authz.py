"""Unit tests for the admin-classification predicate.

Admin status is derived, not stored: a non-guest user whose email domain is in
``ADMIN_EMAIL_DOMAINS`` (exact, case-insensitive match on the part after the
final ``@``) is an admin. The tests pin the security-relevant edges — lookalike
domains, subdomains, guests — so the predicate can never drift into a substring
match.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

from habagou.authz import is_admin
from habagou.config import settings
from habagou.models import User


def _user(email: str | None, *, is_guest: bool = False) -> User:
    # A transient User (never persisted) is enough: is_admin only reads
    # attributes.
    return User(email=email, is_guest=is_guest)


def test_admin_domain_email_is_admin() -> None:
    assert is_admin(_user("matt@mattjmcnaughton.com")) is True


def test_domain_match_is_case_insensitive() -> None:
    assert is_admin(_user("Matt@MATTJMCNAUGHTON.COM")) is True


def test_other_domain_is_not_admin() -> None:
    assert is_admin(_user("matt@example.com")) is False


def test_lookalike_suffix_domain_is_not_admin() -> None:
    assert is_admin(_user("matt@notmattjmcnaughton.com")) is False


def test_subdomain_is_not_admin() -> None:
    assert is_admin(_user("matt@sub.mattjmcnaughton.com")) is False


def test_missing_email_is_not_admin() -> None:
    assert is_admin(_user(None)) is False


def test_email_without_at_sign_is_not_admin() -> None:
    assert is_admin(_user("mattjmcnaughton.com")) is False


def test_guest_with_admin_email_is_not_admin() -> None:
    assert is_admin(_user("matt@mattjmcnaughton.com", is_guest=True)) is False


def test_extra_configured_domain_is_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        settings, "admin_email_domains", "mattjmcnaughton.com, Example.ORG"
    )
    assert is_admin(_user("a@example.org")) is True
    assert is_admin(_user("a@mattjmcnaughton.com")) is True
