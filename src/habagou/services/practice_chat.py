"""Conversational practice tutor agent (WF-16, ADR 0011).

A pydantic-ai agent that chats with the learner in beginner-level simplified
Chinese on a learner-chosen topic. Unlike pack generation there is no corpus
grounding — nothing in a conversation is traced — so the agent is just a
system prompt plus a structured ``PracticeTurn`` output: per-sentence
hanzi/pinyin/English segments and an optional English "break glass" aside.

Conversation state is client-held (the same opaque message-history round trip
as pack generation — see :mod:`habagou.services.message_history`); nothing is
persisted server-side and no database session is involved anywhere in a turn.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog
from pydantic_ai import Agent

from habagou.config import settings
from habagou.dtos.practice import PracticeTurn
from habagou.services.openrouter import build_openrouter_model

if TYPE_CHECKING:
    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models.openai import OpenAIChatModel

SYSTEM_PROMPT = """\
You are a friendly Chinese conversation partner inside an app for beginner \
learners of simplified Chinese. The learner's first message names the topic \
they want to practice; open the conversation yourself with a short greeting \
or question about that topic — never wait for them to make the first move.

Every reply is a list of segments, one segment per sentence, each carrying \
the sentence three ways: hanzi (simplified characters), pinyin (with tone \
marks, e.g. "nǐ hǎo", never "ni3 hao3"), and a natural English translation. \
Keep replies to 1-3 short segments sized for a beginner: HSK 1-2 vocabulary, \
simple grammar, everyday phrasing. End each turn with a simple question or \
prompt that invites the learner's next message.

The learner may write in Chinese, English, or a mix — meet them where they \
are, but always reply in Chinese segments. When they make a small mistake, \
weave the natural phrasing into your reply instead of lecturing.

Use english_aside ONLY when the learner asks for help understanding — \
"what does that mean", "explain that", "in English please", or clear \
confusion. Put a brief English explanation there, and still include Chinese \
segments that continue the conversation in the same turn. Otherwise leave \
english_aside unset.\
"""


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


def _build_practice_agent() -> Agent[None, PracticeTurn]:
    """Assemble the practice agent: system prompt + structured turn output.

    Built WITHOUT a bound model so it can be imported and unit tested with no
    configuration and no network: the run path supplies the model at call time
    (:func:`_build_model`), and tests inject a ``TestModel``/``FunctionModel``
    via the run's ``model=`` argument or ``agent.override``. No tools and no
    output validator — practice needs no corpus grounding.
    """
    # Explicit specialization: ty otherwise mis-infers the agent's output type.
    return Agent[None, PracticeTurn](
        output_type=PracticeTurn,
        system_prompt=SYSTEM_PROMPT,
    )


# Built once at import time; safe because no model is bound (no network, no
# configuration required). Routers depend on it via ``get_practice_agent``.
_practice_agent = _build_practice_agent()


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
