"""Conversational practice service: run the tutor agent (WF-16, ADR 0011).

The agent itself — system prompt and structured ``PracticeTurn`` assembly —
lives in :mod:`habagou.agents.practice` so it can be imported (and evaluated,
see ``docs/evals.md``) with no FastAPI or configuration. This module owns the
application-side wiring: config gating, OpenRouter model resolution, and run
logging.

Conversation state is client-held (the same opaque message-history round trip
as pack generation — see :mod:`habagou.services.message_history`); nothing is
persisted server-side and no database session is involved anywhere in a turn.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from habagou.agents.practice import build_practice_agent
from habagou.config import settings
from habagou.services.openrouter import build_openrouter_model

if TYPE_CHECKING:
    from pydantic_ai import Agent
    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models.openai import OpenAIChatModel

    from habagou.dtos.practice import PracticeTurn


class PracticeNotConfiguredError(RuntimeError):
    """Raised when a practice turn is attempted without model configuration.

    The router maps this to a "practice disabled" 503 instead of a 500 when
    ``settings.practice_configured`` is False (no OpenRouter key).
    """


@dataclass(frozen=True)
class PracticeTurnResult:
    """What a practice turn returns: the tutor reply plus the full history.

    ``messages`` is the complete conversation after the run (prior turns plus
    this turn's request and response); the router serializes it back to the
    client, which replays it on the next turn — conversations are ephemeral
    and client-held by design (ADR 0011).
    """

    turn: PracticeTurn
    messages: list[ModelMessage]


# Built once at import time; safe because no model is bound (no network, no
# configuration required). Routers depend on it via ``get_practice_agent``.
_practice_agent = build_practice_agent()


def get_practice_agent() -> Agent[None, PracticeTurn]:
    """FastAPI dependency returning the shared practice agent.

    Trivial and argument-free so integration/e2e tests can swap it wholesale
    via ``app.dependency_overrides[get_practice_agent]``.
    """
    return _practice_agent


def _build_model(model_id: str | None = None) -> OpenAIChatModel:
    """Return the OpenRouter-backed model for a practice turn.

    Lazy and gated: only built when practice is configured, then cached for
    reuse by the shared :mod:`habagou.services.openrouter` builder.
    ``PRACTICE_MODEL`` is independent of ``GENERATION_MODEL`` so chat can run
    a cheaper/faster model than pack drafting without a code change.
    ``model_id`` is the admin-selected override (already allowlist-validated
    at the API boundary); ``None`` runs the configured default.
    """
    if not settings.practice_configured:
        raise PracticeNotConfiguredError(
            "Conversational practice is not configured: set OPENROUTER_API_KEY "
            "(and PRACTICE_MODEL) to enable it."
        )
    return build_openrouter_model(model_id or settings.practice_model)


async def run_practice_turn(
    agent: Agent[None, PracticeTurn],
    *,
    message: str,
    history: list[ModelMessage] | None = None,
    model_id: str | None = None,
) -> PracticeTurnResult:
    """Run one tutor turn for ``message`` and return the reply plus history.

    Supplies the OpenRouter model at call time (``model_id`` overrides the
    configured default for admin callers) and threads the prior client-held
    ``history`` so the conversation keeps context. The first turn of a
    conversation has no history and its ``message`` is the learner's topic
    (the system prompt tells the tutor to open from it).
    """
    logger = structlog.get_logger("habagou.practice")
    # An empty client-held history is a fresh first turn (pydantic-ai treats []
    # like None), so only a non-empty history counts as a follow-up.
    follow_up = bool(history)
    # Resolved for logging so per-model comparisons never depend on knowing the
    # server default at read time.
    model = model_id or settings.practice_model
    started_at = time.monotonic()
    try:
        result = await agent.run(
            message,
            model=_build_model(model_id),
            message_history=history,
        )
    except Exception:
        # Provider errors and schema-retry exhaustion raise here; log them so
        # they are not invisible to the latency metric.
        logger.warning(
            "practice_run_failed",
            duration_ms=round((time.monotonic() - started_at) * 1000),
            follow_up=follow_up,
            model=model,
        )
        raise
    logger.info(
        "practice_run_completed",
        model_requests=result.usage.requests,
        duration_ms=round((time.monotonic() - started_at) * 1000),
        follow_up=follow_up,
        model=model,
    )
    return PracticeTurnResult(turn=result.output, messages=result.all_messages())
