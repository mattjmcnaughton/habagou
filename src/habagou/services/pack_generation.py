"""Pack-generation service: run the agent and persist finalized drafts.

The agent itself — system prompt, ``find_characters`` grounding tool, corpus
output validator, and assembly — lives in :mod:`habagou.agents.generation` so
it can be imported (and evaluated, see ``docs/evals.md``) with no FastAPI,
configuration, or database. This module owns the application-side wiring:
config gating, OpenRouter model resolution, run logging, and saving a
finalized draft as an owned pack (grounding layer 3 via the repository).
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from habagou.agents.generation import GenerationDeps, build_generation_agent
from habagou.config import settings
from habagou.repositories.characters import CharacterRepository
from habagou.repositories.packs import (
    PackCharacterInput,
    PackRepository,
    PackSentenceInput,
)
from habagou.services.openrouter import build_openrouter_model

if TYPE_CHECKING:
    import uuid

    from pydantic_ai import Agent
    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models.openai import OpenAIChatModel
    from sqlalchemy.ext.asyncio import AsyncSession

    from habagou.dtos.generation import PackDraft
    from habagou.models import Pack


class GenerationNotConfiguredError(RuntimeError):
    """Raised when a generation run is attempted without model configuration.

    The router batch maps this to a "generation disabled" response instead of a
    500 when ``settings.generation_configured`` is False (no OpenRouter key).
    """


@dataclass(frozen=True)
class GenerationResult:
    """What a generation run returns: the draft plus the full message history.

    ``messages`` is the complete conversation after the run (prior turns plus
    this turn's request and response); the router persists it client-side so a
    later refinement turn can be replayed as ``message_history``. Use
    :func:`habagou.services.message_history.dump_message_history` /
    :func:`habagou.services.message_history.load_message_history` to
    (de)serialize it — see HAB-082.
    """

    draft: PackDraft
    messages: list[ModelMessage]


# Built once at import time; safe because no model is bound (no network, no
# configuration required). Routers depend on it via ``get_generation_agent``.
_generation_agent = build_generation_agent()


def get_generation_agent() -> Agent[GenerationDeps, PackDraft]:
    """FastAPI dependency returning the shared generation agent.

    Trivial and argument-free so integration/e2e tests can swap it wholesale via
    ``app.dependency_overrides[get_generation_agent]``.
    """
    return _generation_agent


def _build_model(model_id: str | None = None) -> OpenAIChatModel:
    """Return the OpenRouter-backed model for a generation run.

    Lazy and gated: only built when generation is configured, then cached for
    reuse by the shared :mod:`habagou.services.openrouter` builder.
    ``model_id`` is the admin-selected override (already allowlist-validated at
    the API boundary); ``None`` runs the configured default.
    """
    if not settings.generation_configured:
        raise GenerationNotConfiguredError(
            "Pack generation is not configured: set OPENROUTER_API_KEY (and "
            "GENERATION_MODEL) to enable it."
        )
    return build_openrouter_model(model_id or settings.generation_model)


async def generate_pack_draft(
    agent: Agent[GenerationDeps, PackDraft],
    *,
    session: AsyncSession,
    topic: str,
    history: list[ModelMessage] | None = None,
    model_id: str | None = None,
) -> GenerationResult:
    """Run the agent to draft a pack for ``topic`` and return draft + history.

    Assembles :class:`~habagou.agents.generation.GenerationDeps` around a real
    ``CharacterRepository`` bound to ``session``, supplies the OpenRouter model
    at call time (``model_id`` overrides the configured default for admin
    callers), and threads prior ``history`` so refinement turns keep context
    (HAB-082). Returns the validated
    :class:`~habagou.dtos.generation.PackDraft` alongside the full updated
    message history for the caller to persist.
    """
    deps = GenerationDeps(characters=CharacterRepository(session))
    logger = structlog.get_logger("habagou.generation")
    # An empty client-held history is a fresh first turn (pydantic-ai treats []
    # like None), so only a non-empty history counts as a refinement.
    refinement = bool(history)
    # Resolved for logging so per-model comparisons never depend on knowing the
    # server default at read time.
    model = model_id or settings.generation_model
    started_at = time.monotonic()
    try:
        result = await agent.run(
            topic,
            deps=deps,
            model=_build_model(model_id),
            message_history=history,
        )
    except Exception:
        # The worst latency cases (retry exhaustion, provider errors) raise here;
        # log them too so they are not invisible to the round-trip metric.
        logger.warning(
            "generation_run_failed",
            duration_ms=round((time.monotonic() - started_at) * 1000),
            refinement=refinement,
            model=model,
        )
        raise
    # ``requests`` is pydantic-ai's own count of model round trips for this run;
    # it is the signal for whether the corpus-in-prompt change (Move A) actually
    # cut the guess -> find_characters -> retry loop that dominates latency.
    logger.info(
        "generation_run_completed",
        model_requests=result.usage.requests,
        duration_ms=round((time.monotonic() - started_at) * 1000),
        refinement=refinement,
        model=model,
    )
    return GenerationResult(draft=result.output, messages=result.all_messages())


# --- HAB-084: persist a finalized draft as an owned pack -----------------------

# The curated palette owned packs draw from (mirrors the seed packs' colors in
# ``scripts.seed.SEED_PACKS``). A draft carries no color, so one is picked
# deterministically from the title (below).
_CURATED_COLORS: tuple[str, ...] = ("#c4633f", "#3f8a86", "#5b5fa8", "#b5852e")

# Owned packs sort after the curated packs (whose sort_order is 1-4), tie-broken
# by id — matching ``PackRepository.list_visible``'s ``(sort_order, id)`` order.
_OWNED_PACK_SORT_ORDER = 1000


def _color_for_title(title: str) -> str:
    """Deterministically pick a curated color for a pack title.

    Keyed on a stable hash of the title (not Python's per-process salted
    ``hash``) so the same title always yields the same color across processes.
    """
    digest = hashlib.sha256(title.encode("utf-8")).digest()
    return _CURATED_COLORS[digest[0] % len(_CURATED_COLORS)]


async def save_pack_draft(
    session: AsyncSession,
    *,
    draft: PackDraft,
    owner_id: uuid.UUID,
) -> Pack:
    """Persist a finalized :class:`PackDraft` as a pack owned by ``owner_id``.

    Supplies the save-time defaults a draft omits — ``glyph`` (the first
    character's hanzi), ``color`` (a deterministic curated pick, see
    :func:`_color_for_title`), and ``sort_order`` (:data:`_OWNED_PACK_SORT_ORDER`,
    so owned packs list after curated ones) — maps the draft's characters and
    sentences onto the repository's input value objects, and commits. The
    repository re-validates every glyph against the corpus (grounding layer 3),
    raising ``ValueError`` for any non-corpus glyph; that propagates to the
    caller, which surfaces it as a 422.
    """
    pack = await PackRepository(session).create(
        owner_id=owner_id,
        title=draft.title,
        glyph=draft.characters[0].hanzi,
        color=_color_for_title(draft.title),
        sort_order=_OWNED_PACK_SORT_ORDER,
        characters=[
            PackCharacterInput(
                hanzi=character.hanzi,
                pinyin=character.pinyin,
                meaning=character.meaning,
            )
            for character in draft.characters
        ],
        sentences=[
            PackSentenceInput(
                hanzi=sentence.hanzi,
                pinyin=sentence.pinyin,
                translation=sentence.translation,
            )
            for sentence in draft.sentences
        ],
    )
    await session.commit()
    return pack
