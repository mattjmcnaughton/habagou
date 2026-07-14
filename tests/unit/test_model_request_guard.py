"""Proves the suite-wide real-model-request guard (HAB-086).

``tests/conftest.py`` sets ``pydantic_ai.models.ALLOW_MODEL_REQUESTS = False`` so
an un-stubbed agent run against a live model raises rather than hitting the
network, while stubbed ``TestModel`` runs still work.
"""

from __future__ import annotations

import pydantic_ai.models
import pytest
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.providers.openrouter import OpenRouterProvider


def test_guard_is_active() -> None:
    assert pydantic_ai.models.ALLOW_MODEL_REQUESTS is False


def test_unstubbed_real_model_request_raises() -> None:
    model = OpenAIChatModel(
        "openai/gpt-4o", provider=OpenRouterProvider(api_key="dummy")
    )
    agent = Agent(model)
    with pytest.raises(RuntimeError, match="ALLOW_MODEL_REQUESTS is False"):
        agent.run_sync("hello")


def test_test_model_still_works() -> None:
    agent = Agent(TestModel())
    result = agent.run_sync("hello")
    assert result.output
