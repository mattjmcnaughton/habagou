"""Unit tests for application settings helpers."""

import pytest

from habagou.config import Settings, normalize_database_url


def test_normalize_database_url_rewrites_neon_style_url() -> None:
    raw = (
        "postgresql://neondb_owner:secret@ep-x.neon.tech/neondb"
        "?sslmode=require&channel_binding=require"
    )
    assert normalize_database_url(raw) == (
        "postgresql+asyncpg://neondb_owner:secret@ep-x.neon.tech/neondb?ssl=require"
    )


def test_normalize_database_url_strips_channel_binding_only() -> None:
    raw = "postgresql+asyncpg://u:p@host/db?ssl=require&channel_binding=require"
    assert normalize_database_url(raw) == (
        "postgresql+asyncpg://u:p@host/db?ssl=require"
    )


def test_normalize_database_url_leaves_asyncpg_url_alone() -> None:
    url = "postgresql+asyncpg://habagou:habagou@localhost:5432/habagou?ssl=require"
    assert normalize_database_url(url) == url


def test_settings_normalizes_database_url_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgres://u:p@host/db?sslmode=require&channel_binding=require",
    )
    settings = Settings()
    assert settings.database_url == "postgresql+asyncpg://u:p@host/db?ssl=require"
