"""Unit tests for the practice-status route handler (entry-point gating).

The status probe exists so the practice screen can show an unavailable state
(instead of the topic picker) when conversational practice is unconfigured.
These tests call the ``get_practice_status`` handler directly and assert the
``enabled`` flag it returns tracks ``settings.practice_configured`` in both
directions, mirroring ``test_generation_status.py``.
"""

import pytest

from habagou.config import settings
from habagou.models import User
from habagou.routers.v1.practice import get_practice_status


@pytest.mark.anyio
async def test_status_enabled_when_practice_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")
    # A transient User stands in for the authenticated caller; it never touches
    # the DB, so no session is needed.
    result = await get_practice_status(User())
    assert result.enabled is True


@pytest.mark.anyio
async def test_status_disabled_when_practice_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    result = await get_practice_status(User())
    assert result.enabled is False


# --- Admin model selection: status carries the picker options for admins --------


@pytest.mark.anyio
async def test_status_lists_models_for_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")
    monkeypatch.setattr(settings, "practice_model", "openai/gpt-5.6-terra")
    admin = User(email="matt@mattjmcnaughton.com", is_guest=False)

    result = await get_practice_status(admin)

    assert result.enabled is True
    assert result.default_model == "openai/gpt-5.6-terra"
    assert result.models is not None
    assert [option.id for option in result.models] == [
        "openai/gpt-5.6-terra",
        "anthropic/claude-sonnet-5",
        "minimax/minimax-m3",
    ]


@pytest.mark.anyio
async def test_status_hides_models_from_non_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")

    result = await get_practice_status(User(email="dev@example.com"))

    assert result.enabled is True
    assert result.models is None
    assert result.default_model is None
