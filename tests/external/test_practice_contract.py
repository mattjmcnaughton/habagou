"""Live-provider contract test for conversational practice (WF-16).

One real round trip against the configured OpenRouter practice model, to catch
drift in the tutor prompt, the ``PracticeTurn`` output schema, or the model's
ability to fill every segment three ways (hanzi/pinyin/English). Quarantined in
``tests/external/`` behind ``@pytest.mark.external`` — reachable only via
``just test-external`` — and keyless-safe: it skips cleanly when
``OPENROUTER_API_KEY`` is unset.

No database and no stubs beyond lifting the suite-wide model-request guard:
practice has no corpus grounding, so the real module agent and the real
``_build_model()`` output run as-is.
"""

from __future__ import annotations

import pytest
from pydantic_ai.models import override_allow_model_requests

from habagou.config import settings
from habagou.dtos.practice import PracticeTurn
from habagou.services.practice_chat import _build_model, get_practice_agent


def _has_cjk(text: str) -> bool:
    return any("一" <= char <= "鿿" for char in text)


@pytest.mark.external
@pytest.mark.anyio
async def test_live_provider_returns_structured_practice_turn() -> None:
    if not settings.openrouter_api_key:
        pytest.skip("OPENROUTER_API_KEY is unset; skipping live provider contract test")

    agent = get_practice_agent()

    with override_allow_model_requests(True):
        result = await agent.run(
            "ordering food at a restaurant",
            model=_build_model(),
        )

    turn = result.output
    # The output schema still binds: a well-formed PracticeTurn came back.
    assert isinstance(turn, PracticeTurn)
    assert len(turn.segments) >= 1
    for segment in turn.segments:
        # Every segment carries the sentence three ways: real hanzi, non-empty
        # pinyin, and a non-empty English translation.
        assert _has_cjk(segment.hanzi), f"segment without hanzi: {segment.hanzi!r}"
        assert segment.pinyin.strip()
        assert segment.english.strip()
        # The prompt demands tone marks, not tone digits ("nǐ", never "ni3").
        assert not any(char.isdigit() for char in segment.pinyin), segment.pinyin
