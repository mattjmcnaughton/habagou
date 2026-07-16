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
