"""Unit tests for the feature-flag registry, settings parsing, and resolution."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, cast

import pytest

from habagou.config import Settings, settings
from habagou.models import User
from habagou.services import feature_flags
from habagou.services.feature_flags import FeatureFlagService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _user() -> User:
    return User(id=uuid.uuid4(), username="flag-user", display_name="Flag User")


def _service(repository: object) -> FeatureFlagService:
    service = FeatureFlagService(cast("AsyncSession", object()))
    service.repository = cast("feature_flags.FeatureFlagRepository", repository)
    return service


class StubFeatureFlagRepository:
    def __init__(
        self,
        overrides: dict[str, bool] | None = None,
        counts: dict[str, int] | None = None,
    ) -> None:
        self.overrides = overrides or {}
        self.counts = counts or {}

    async def overrides_for_user(self, *, user_id: uuid.UUID) -> dict[str, bool]:
        return self.overrides

    async def override_counts(self) -> dict[str, int]:
        return self.counts


class ExplodingRepository:
    async def overrides_for_user(self, *, user_id: uuid.UUID) -> dict[str, bool]:
        raise AssertionError("must not query the database for an empty registry")


def test_feature_flag_default_map_parses_and_drops_malformed() -> None:
    parsed = Settings(
        feature_flag_defaults=" alpha:on , beta:OFF ,bad, gamma:maybe , :on ,"
    ).feature_flag_default_map
    assert parsed == {"alpha": True, "beta": False}


def test_feature_flag_default_map_empty_by_default() -> None:
    assert Settings(feature_flag_defaults="").feature_flag_default_map == {}


def test_effective_defaults_applies_settings_over_code_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(feature_flags, "FLAG_DEFAULTS", {"alpha": False, "beta": True})
    monkeypatch.setattr(settings, "feature_flag_defaults", "alpha:on,unknown:on")

    assert feature_flags.effective_defaults() == {"alpha": True, "beta": True}
    assert feature_flags.known_flag_keys() == frozenset({"alpha", "beta"})


@pytest.mark.anyio
async def test_resolve_for_user_prefers_override_and_drops_stale_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(feature_flags, "FLAG_DEFAULTS", {"alpha": False, "beta": True})
    monkeypatch.setattr(settings, "feature_flag_defaults", "")
    service = _service(
        StubFeatureFlagRepository(overrides={"alpha": True, "removed_flag": True})
    )

    resolved = await service.resolve_for_user(_user())

    assert resolved == {"alpha": True, "beta": True}


@pytest.mark.anyio
async def test_resolve_for_user_empty_registry_skips_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(feature_flags, "FLAG_DEFAULTS", {})
    service = _service(ExplodingRepository())

    assert await service.resolve_for_user(_user()) == {}


@pytest.mark.anyio
async def test_list_flags_sorted_with_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(feature_flags, "FLAG_DEFAULTS", {"beta": True, "alpha": False})
    monkeypatch.setattr(settings, "feature_flag_defaults", "")
    service = _service(StubFeatureFlagRepository(counts={"beta": 3, "stale": 9}))

    listed = await service.list_flags()

    assert [(f.key, f.enabled_default, f.override_count) for f in listed] == [
        ("alpha", False, 0),
        ("beta", True, 3),
    ]
