"""Unit tests for the generation-status route handler (entry-point gating).

The status probe exists so the frontend can hide the "Create a pack" entry point
when agent generation is unconfigured (issue #102). These tests call the
``get_generation_status`` handler directly and assert the ``enabled`` flag it
returns tracks ``settings.generation_configured`` in both directions, so a
regression in the handler (e.g. hardcoding the flag) is caught — re-deriving the
DTO in the test would not exercise the handler at all.
"""

import pytest

from habagou.config import settings
from habagou.models import User
from habagou.routers.v1.generation import get_generation_status


@pytest.mark.anyio
async def test_status_enabled_when_generation_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")
    # A transient User stands in for the authenticated caller; it never touches
    # the DB, so no session is needed.
    result = await get_generation_status(User())
    assert result.enabled is True


@pytest.mark.anyio
async def test_status_disabled_when_generation_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    result = await get_generation_status(User())
    assert result.enabled is False


# --- Admin model selection: status carries the picker options for admins --------


@pytest.mark.anyio
async def test_status_lists_models_for_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")
    monkeypatch.setattr(settings, "generation_model", "openai/gpt-5.6-terra")
    admin = User(email="matt@mattjmcnaughton.com", is_guest=False)

    result = await get_generation_status(admin)

    assert result.enabled is True
    assert result.default_model == "openai/gpt-5.6-terra"
    assert result.models is not None
    assert [option.id for option in result.models] == [
        "openai/gpt-5.6-terra",
        "anthropic/claude-sonnet-5",
        "minimax/minimax-m3",
    ]
    assert result.models[1].label == "Claude Sonnet 5"
    assert result.models[2].label == "MiniMax M3"


@pytest.mark.anyio
async def test_status_hides_models_from_non_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")

    result = await get_generation_status(User(email="dev@example.com"))

    assert result.enabled is True
    assert result.models is None
    assert result.default_model is None


@pytest.mark.anyio
async def test_status_hides_models_when_unconfigured_even_for_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    admin = User(email="matt@mattjmcnaughton.com", is_guest=False)

    result = await get_generation_status(admin)

    assert result.enabled is False
    assert result.models is None
    assert result.default_model is None
