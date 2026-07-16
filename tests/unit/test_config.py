"""Unit tests for application settings helpers."""

from pathlib import Path

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


def test_generation_defaults_unset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("GENERATION_MODEL", raising=False)
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    assert settings.openrouter_api_key == ""
    assert settings.generation_model == "deepseek/deepseek-v4-flash"
    assert settings.generation_configured is False
    assert settings.logfire_token == ""


def test_logfire_token_reads_from_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LOGFIRE_TOKEN", "test-logfire-token")
    settings = Settings()
    assert settings.logfire_token == "test-logfire-token"


def test_generation_configured_true_when_key_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    settings = Settings()
    assert settings.generation_configured is True


def test_generation_configured_false_when_model_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("GENERATION_MODEL", "")
    settings = Settings()
    assert settings.generation_configured is False


def test_create_app_boots_with_generation_key_unset() -> None:
    from fastapi import FastAPI

    from habagou.app import create_app

    assert isinstance(create_app(), FastAPI)
