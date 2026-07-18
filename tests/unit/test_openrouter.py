"""Unit tests for the shared OpenRouter helpers (labels + cached builder)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

from habagou.services import openrouter
from habagou.services.openrouter import build_openrouter_model, model_label


def test_model_label_maps_known_ids() -> None:
    assert model_label("anthropic/claude-sonnet-5") == "Claude Sonnet 5"
    assert model_label("minimax/minimax-m3") == "MiniMax M3"


def test_model_label_falls_back_to_the_id() -> None:
    assert model_label("someone/unmapped-model") == "someone/unmapped-model"


def test_builder_caches_per_model_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(openrouter.settings, "openrouter_api_key", "sk-test")
    monkeypatch.setattr(openrouter, "_model_cache", {})

    first = build_openrouter_model("anthropic/claude-sonnet-5")
    second = build_openrouter_model("minimax/minimax-m3")
    again = build_openrouter_model("anthropic/claude-sonnet-5")

    # Distinct ids get distinct models; the same id reuses the cached instance
    # (the provider owns an httpx pool, so identity matters, not just equality).
    assert first is not second
    assert first is again
    assert first.model_name == "anthropic/claude-sonnet-5"
    assert second.model_name == "minimax/minimax-m3"
