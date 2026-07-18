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
    assert settings.generation_model == "openai/gpt-5.6-terra"
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


def test_admin_email_domains_default_and_parsing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    assert settings.admin_email_domains == "mattjmcnaughton.com"
    assert settings.admin_email_domain_set == frozenset({"mattjmcnaughton.com"})


def test_admin_email_domain_set_splits_strips_and_lowercases(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ADMIN_EMAIL_DOMAINS", " MattJMcNaughton.com ,example.org,, ")
    settings = Settings()
    assert settings.admin_email_domain_set == frozenset(
        {"mattjmcnaughton.com", "example.org"}
    )


def test_generation_model_ids_prepend_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    # Default model first (it is the implicit selection), then the admin list
    # in configured order.
    assert settings.generation_model_ids == (
        "openai/gpt-5.6-terra",
        "anthropic/claude-sonnet-5",
        "minimax/minimax-m3",
    )
    assert settings.practice_model_ids == settings.generation_model_ids


def test_model_ids_dedupe_when_default_is_also_listed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "ADMIN_CHAT_MODELS", " anthropic/claude-sonnet-5 ,openai/gpt-5.6-terra,"
    )
    settings = Settings()
    assert settings.generation_model_ids == (
        "openai/gpt-5.6-terra",
        "anthropic/claude-sonnet-5",
    )


def test_practice_model_ids_use_the_practice_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRACTICE_MODEL", "openai/gpt-5.6-mini")
    settings = Settings()
    assert settings.practice_model_ids == (
        "openai/gpt-5.6-mini",
        "anthropic/claude-sonnet-5",
        "minimax/minimax-m3",
    )
