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
