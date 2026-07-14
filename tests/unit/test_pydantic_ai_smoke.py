"""Import smoke test for the pydantic-ai dependency (HAB-076).

Verifies the pieces the agent pack-generation work depends on are importable
from the resolved ``pydantic-ai-slim[openai]`` package: the top-level module,
the test models, and the OpenRouter provider.
"""

from __future__ import annotations


def test_pydantic_ai_imports() -> None:
    import pydantic_ai
    from pydantic_ai import Agent, models
    from pydantic_ai.models.function import FunctionModel
    from pydantic_ai.models.test import TestModel
    from pydantic_ai.providers.openrouter import OpenRouterProvider

    assert pydantic_ai.__version__
    assert TestModel is not None
    assert FunctionModel is not None
    assert OpenRouterProvider is not None
    assert hasattr(Agent, "override")
    assert hasattr(models, "ALLOW_MODEL_REQUESTS")
