"""Feature-flag registry and per-user resolution.

Flags are defined in code: add a :class:`FeatureFlag` member and a default in
``FLAG_DEFAULTS`` to introduce one. Defaults can be flipped globally without a
deploy of code via ``settings.feature_flag_defaults``, and per user via
``user_feature_overrides`` rows managed through the admin API.
Resolution order: per-user override > settings default > code default. Keys
absent from the registry — stale settings entries or database rows for deleted
flags — are ignored, so removing a flag from code needs no data migration.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from habagou.config import settings
from habagou.dtos.feature_flags import FeatureFlagDTO
from habagou.repositories import FeatureFlagRepository, UserRepository

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from habagou.models import User


class FeatureFlag(StrEnum):
    """Canonical feature flags; the registry is empty until the first flag."""


# Code defaults per flag. Every FeatureFlag member gets an entry here; a flag
# missing from this dict does not exist as far as resolution is concerned.
FLAG_DEFAULTS: dict[FeatureFlag, bool] = {}


def known_flag_keys() -> frozenset[str]:
    """The registered flag keys (StrEnum members are their string keys)."""
    return frozenset(str(flag) for flag in FLAG_DEFAULTS)


def effective_defaults() -> dict[str, bool]:
    """Code defaults with ``settings.feature_flag_defaults`` applied on top."""
    defaults = {str(flag): enabled for flag, enabled in FLAG_DEFAULTS.items()}
    for key, enabled in settings.feature_flag_default_map.items():
        if key in defaults:
            defaults[key] = enabled
    return defaults


class FeatureFlagService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = FeatureFlagRepository(session)
        self.user_repository = UserRepository(session)

    async def resolve_for_user(self, user: User) -> dict[str, bool]:
        """The user's effective flag map: their override where set, else the default."""
        defaults = effective_defaults()
        if not defaults:
            return {}
        overrides = await self.repository.overrides_for_user(user_id=user.id)
        return {key: overrides.get(key, enabled) for key, enabled in defaults.items()}

    async def list_flags(self) -> list[FeatureFlagDTO]:
        """Every registered flag with its effective default and override count."""
        counts = await self.repository.override_counts()
        return [
            FeatureFlagDTO(
                key=key,
                enabled_default=enabled,
                override_count=counts.get(key, 0),
            )
            for key, enabled in sorted(effective_defaults().items())
        ]

    async def set_user_override(
        self, *, flag_key: str, user_id: uuid.UUID, enabled: bool
    ) -> bool:
        """Upsert a user's override; False if the user does not exist.

        The row lock holds the user in place until the commit, so a concurrent
        user deletion cannot slip between the existence check and the insert.
        """
        if await self.user_repository.lock_by_id(user_id) is None:
            return False
        await self.repository.set_override(
            user_id=user_id, flag_key=flag_key, enabled=enabled
        )
        await self.session.commit()
        return True

    async def clear_user_override(self, *, flag_key: str, user_id: uuid.UUID) -> bool:
        """Delete a user's override; False if none existed."""
        deleted = await self.repository.delete_override(
            user_id=user_id, flag_key=flag_key
        )
        await self.session.commit()
        return deleted
