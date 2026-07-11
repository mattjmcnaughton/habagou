"""Authentication service logic."""

from __future__ import annotations

from typing import TYPE_CHECKING

from habagou.repositories import UserRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from habagou.auth import AuthIdentity
    from habagou.models import User


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    async def sign_in(self, identity: AuthIdentity) -> User:
        user = await self.users.get_by_identity(identity.issuer, identity.subject)
        if user is None:
            user = await self.users.create(
                username=await self._available_username(identity.username),
                display_name=identity.display_name,
                auth_issuer=identity.issuer,
                auth_subject=identity.subject,
                email=identity.email,
            )
        else:
            user.display_name = identity.display_name
            user.email = identity.email
            await self.session.flush()

        await self.session.commit()
        return user

    async def _available_username(self, preferred: str) -> str:
        base = _normalize_username(preferred)
        candidate = base
        suffix = 2
        while await self.users.username_exists(candidate):
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate


def _normalize_username(username: str) -> str:
    normalized = username.strip().lower().replace(" ", "-")
    return normalized or "user"
