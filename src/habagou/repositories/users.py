"""Data access for learner accounts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from habagou.models import User

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def lock_by_id(self, user_id: uuid.UUID) -> User | None:
        """Lock a user's row until the current transaction finishes."""
        result = await self.session.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_by_identity(self, issuer: str, subject: str) -> User | None:
        result = await self.session.execute(
            select(User).where(
                User.auth_issuer == issuer,
                User.auth_subject == subject,
            )
        )
        return result.scalar_one_or_none()

    async def username_exists(self, username: str) -> bool:
        result = await self.session.execute(
            select(User.id).where(User.username == username)
        )
        return result.scalar_one_or_none() is not None

    async def create(
        self,
        *,
        username: str,
        display_name: str,
        auth_issuer: str,
        auth_subject: str,
        email: str | None,
    ) -> User:
        user = User(
            username=username,
            display_name=display_name,
            is_guest=False,
            auth_issuer=auth_issuer,
            auth_subject=auth_subject,
            email=email,
        )
        self.session.add(user)
        await self.session.flush()
        return user
