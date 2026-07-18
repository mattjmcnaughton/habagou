"""Shared OpenRouter model construction for agent features.

Pack generation and conversational practice both run OpenAI-compatible models
through OpenRouter with the same API key but independently configured model
ids. The provider owns an ``httpx.AsyncClient``, so built models are cached
and reused across runs (mirroring ``db.py``'s shared engine) instead of
leaking a fresh connection pool per request.
"""

from __future__ import annotations

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from habagou.config import settings

# Keyed on (model name, API key) so tests that flip configuration get a
# matching model. Growth is bounded by the distinct configurations seen in one
# process — a handful outside of tests.
_model_cache: dict[tuple[str, str], OpenAIChatModel] = {}

# Display names for the admin model picker. Ids outside this map (e.g. an
# operator-configured default) fall back to the raw OpenRouter id, which is
# accurate if less pretty — never a blocker for adding a model.
_MODEL_LABELS = {
    "anthropic/claude-sonnet-5": "Claude Sonnet 5",
    "minimax/minimax-m3": "MiniMax M3",
    "openai/gpt-5.6-terra": "GPT-5.6 Terra",
}


def model_label(model_id: str) -> str:
    """Human-readable picker label for an OpenRouter model id."""
    return _MODEL_LABELS.get(model_id, model_id)


def build_openrouter_model(model_name: str) -> OpenAIChatModel:
    """Return a cached OpenRouter-backed model for ``model_name``.

    Constructing the model performs no network I/O; the request happens when
    an agent runs. Callers gate on their feature's ``*_configured`` setting
    before calling, so the key is assumed present here.
    """
    key = (model_name, settings.openrouter_api_key)
    model = _model_cache.get(key)
    if model is None:
        model = OpenAIChatModel(
            model_name,
            provider=OpenRouterProvider(api_key=settings.openrouter_api_key),
        )
        _model_cache[key] = model
    return model
