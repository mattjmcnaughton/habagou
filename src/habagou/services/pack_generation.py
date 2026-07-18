"""Grounding pieces for the agent pack-generation flow (Epic 7).

A generated pack may only contain hanzi that already live in the stroke corpus
(the ``characters`` table stores ``hanzi``/``stroke_data``/``stroke_count`` and
*no* glosses). The grounding logic keeps the model honest about that.

Layer 1 — :func:`find_characters`: a tool the model calls to learn which of its
candidate hanzi actually exist in the corpus (and how many strokes each takes, a
difficulty signal). It returns corpus *membership only*: the corpus has no
pinyin/meaning, so the model supplies every gloss itself.

Layer 2 — :func:`validate_corpus_membership`: an output validator that rejects a
finished :class:`~habagou.dtos.generation.PackDraft` referencing any non-corpus
hanzi, so pydantic-ai feeds the error back and the model retries. It mirrors the
seed write path (:func:`scripts.seed.required_hanzi`), which requires *every*
character — pack members and each glyph within a sentence — to be in the corpus.

The grounding logic takes a :class:`GenerationDeps` directly (not a
``RunContext``) so it is unit-testable without an agent or a database; the agent
assembly wires it to ``RunContext.deps`` in the next batch.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

import structlog
from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry, RunContext

from habagou.config import settings
from habagou.dtos.generation import PackDraft
from habagou.repositories.characters import CharacterRepository
from habagou.repositories.packs import (
    PackCharacterInput,
    PackRepository,
    PackSentenceInput,
)
from habagou.services.openrouter import build_openrouter_model

if TYPE_CHECKING:
    import uuid
    from collections.abc import Iterable

    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models.openai import OpenAIChatModel
    from sqlalchemy.ext.asyncio import AsyncSession

    from habagou.models import Pack


class CorpusReader(Protocol):
    """The corpus-membership seam the grounding logic depends on.

    :class:`~habagou.repositories.characters.CharacterRepository` satisfies it
    structurally; unit tests supply a lightweight stub so no database is needed.
    """

    async def missing_hanzi(self, hanzi: Iterable[str]) -> set[str]: ...

    async def stroke_counts(self, hanzi: Iterable[str]) -> dict[str, int]: ...

    async def all_hanzi(self) -> tuple[str, ...]: ...


@dataclass(frozen=True)
class GenerationDeps:
    """Dependencies carried into the grounding tool and output validator.

    Holds the corpus seam rather than a raw session so the logic is testable
    against a stub. The agent wires a real ``CharacterRepository`` here.
    """

    characters: CorpusReader


class FoundCharacter(BaseModel):
    """A candidate confirmed to exist in the corpus, with its stroke count."""

    hanzi: str
    stroke_count: int


class CorpusCheck(BaseModel):
    """Result of :func:`find_characters`: corpus MEMBERSHIP only.

    The corpus stores no pinyin/meaning, so this reports nothing but which
    candidates exist (``found``, each with its ``stroke_count`` difficulty
    signal) and which do not (``dropped``). The model must supply every gloss
    itself. Both lists preserve first-seen input order for determinism.
    """

    found: list[FoundCharacter]
    dropped: list[str]


def _unique_characters(candidates: Iterable[str]) -> list[str]:
    """Flatten candidates to individual, deduped hanzi in first-seen order.

    Multi-character strings are split into their component characters (a pack
    traces one glyph at a time, and sentence tracing traces each glyph too), and
    whitespace is dropped. Duplicates collapse to their first appearance.
    """
    seen: set[str] = set()
    ordered: list[str] = []
    for candidate in candidates:
        for char in candidate:
            if char.strip() and char not in seen:
                seen.add(char)
                ordered.append(char)
    return ordered


async def find_characters(deps: GenerationDeps, candidates: list[str]) -> CorpusCheck:
    """Report which candidate hanzi exist in the stroke corpus (layer 1 tool).

    Candidates are normalized (multi-char strings split, whitespace dropped,
    deduped, order preserved). ``found`` carries each existing hanzi with its
    stroke count; ``dropped`` surfaces the candidates absent from the corpus so
    the model learns to avoid them. Returns membership only — never glosses.
    """
    ordered = _unique_characters(candidates)
    if not ordered:
        return CorpusCheck(found=[], dropped=[])

    counts = await deps.characters.stroke_counts(ordered)
    found = [
        FoundCharacter(hanzi=char, stroke_count=counts[char])
        for char in ordered
        if char in counts
    ]
    dropped = [char for char in ordered if char not in counts]
    return CorpusCheck(found=found, dropped=dropped)


# Sentinels around the corpus block in the system prompt. Explicit markers keep
# the ~9k-character run readable to the model (and greppable in tests) without
# per-character separators, which would triple the token cost.
_CORPUS_OPEN = "<corpus>"
_CORPUS_CLOSE = "</corpus>"


async def corpus_membership_prompt(deps: GenerationDeps) -> str:
    """Build the system-prompt block listing every traceable corpus character.

    Handed to the model up front so it can pick pack members directly from the
    corpus instead of guessing from training memory and round-tripping through
    ``find_characters`` to verify them — the round trips that dominate generation
    latency. Membership only (no stroke counts, which would roughly triple the
    block; those stay available via ``find_characters``).

    The character run is a single unbroken, codepoint-sorted string between
    :data:`_CORPUS_OPEN` / :data:`_CORPUS_CLOSE`. It is deterministic so the
    system prompt is byte-identical across the calls of a generation session,
    which is what lets provider-side prompt caching reuse it.
    """
    hanzi = await deps.characters.all_hanzi()
    return (
        "The complete traceable stroke corpus is listed between the markers "
        f"below — all {len(hanzi)} characters that may appear in a pack. Any "
        "character in this list is confirmed traceable and needs no tool check; "
        "any character NOT in it can never be used, no matter how common it "
        f"seems.\n{_CORPUS_OPEN}{''.join(hanzi)}{_CORPUS_CLOSE}"
    )


def _draft_hanzi(draft: PackDraft) -> list[str]:
    """Every hanzi a draft would trace, in first-seen order, deduped.

    Mirrors :func:`scripts.seed.required_hanzi`: the pack's character members
    plus *each* glyph in every sentence (sentences are traced glyph by glyph, so
    every one of their characters must exist in the corpus too). Shares the
    normalization of :func:`_unique_characters`, so stray whitespace never
    reaches the corpus check.
    """
    return _unique_characters(
        [character.hanzi for character in draft.characters]
        + [sentence.hanzi for sentence in draft.sentences]
    )


async def validate_corpus_membership(
    deps: GenerationDeps, draft: PackDraft
) -> PackDraft:
    """Reject a draft referencing hanzi absent from the corpus (layer 2).

    Collects every glyph the draft would trace — characters and each glyph in
    every sentence — and raises :class:`pydantic_ai.ModelRetry` listing the
    offenders when any are missing, so pydantic-ai feeds the message back and the
    model retries. Returns the draft unchanged when every glyph is in the corpus.
    """
    hanzi = _draft_hanzi(draft)
    if not hanzi:
        return draft

    missing = await deps.characters.missing_hanzi(hanzi)
    if missing:
        offenders = "".join(char for char in hanzi if char in missing)
        raise ModelRetry(
            "These characters are not in the stroke corpus and cannot appear in "
            f"the pack: {offenders}. Call find_characters to check membership and "
            "replace or remove them (including inside sentences)."
        )
    return draft


# --- HAB-081: assembled agent, model construction, and service entry point -----

# Retry budget passed to Agent(retries=...). pydantic-ai applies it as two
# independent caps of this size: one on tool-call retries (find_characters)
# and one on output-validation retries (validate_corpus_membership's
# ModelRetry), so a model that never grounds itself still terminates after a
# bounded number of round trips.
_GENERATION_RETRIES = 3

SYSTEM_PROMPT = """\
You build a focused Chinese-character practice pack for a stroke-tracing app \
from the user's topic.

The stroke corpus is the ONLY source of truth for which characters are \
traceable, and the complete corpus is listed for you in this prompt (between \
the <corpus> markers). Your training memory does NOT count: a character you \
"know" exists is unusable unless it appears in that list. Pick every pack \
character and every sentence glyph directly from the corpus list. Use the \
find_characters tool only when you want a character's stroke count as a \
difficulty signal, or to double-check a specific character you are unsure \
about — you do NOT need to call it for characters you can already see in the \
list.

You supply the glosses yourself, because the corpus stores none: give each \
character its pinyin (with tone marks, e.g. "nǐ", not "ni3") and a concise \
English meaning.

Sentences are optional. Include a few short practice sentences only when they \
help; EVERY character in a sentence must also appear in the corpus list, \
because sentences are traced glyph by glyph. By convention sentences are \
punctuation-free: the corpus never contains punctuation, so never write ，, 。, \
？, ！ or any other punctuation mark.

When some characters the user asked for are not in the corpus, say so honestly \
in coverage_note (for example "found 6 of 8 requested characters; 望 and 憧 \
aren't in the corpus yet") rather than silently shrinking the pack and hiding \
the gap.

Keep packs focused: roughly 5-12 characters unless the user asks for a \
different size. On a refinement turn, adjust the previous draft to the new \
request instead of starting over from scratch.\
"""


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
    :func:`dump_message_history` / :func:`load_message_history` to (de)serialize
    it — see HAB-082.
    """

    draft: PackDraft
    messages: list[ModelMessage]


def _build_generation_agent() -> Agent[GenerationDeps, PackDraft]:
    """Assemble the pack-generation agent with tool + validator wired.

    The agent is built WITHOUT a bound model so it can be imported and unit
    tested with no configuration and no network: the run path supplies the model
    at call time (:func:`_build_model`), and tests inject a ``TestModel`` /
    ``FunctionModel`` via the run's ``model=`` argument or ``agent.override``.
    """
    # Explicit specialization: ty otherwise mis-infers the agent's output type.
    agent = Agent[GenerationDeps, PackDraft](
        output_type=PackDraft,
        deps_type=GenerationDeps,
        retries=_GENERATION_RETRIES,
        system_prompt=SYSTEM_PROMPT,
    )

    @agent.system_prompt
    async def _corpus_membership(ctx: RunContext[GenerationDeps]) -> str:
        """Append the full traceable corpus to the system prompt (see Move A).

        Registered without ``dynamic=True`` so pydantic-ai evaluates it once on
        the first turn and replays the resulting ``SystemPromptPart`` verbatim
        from ``message_history`` on refinement turns — keeping the prompt prefix
        byte-identical across a session for provider-side prompt caching.
        """
        return await corpus_membership_prompt(ctx.deps)

    @agent.tool(name="find_characters")
    async def _find_characters(
        ctx: RunContext[GenerationDeps], candidates: list[str]
    ) -> CorpusCheck:
        """Check which candidate hanzi exist in the traceable stroke corpus.

        Pass the characters (or short strings) you are considering. Multi-glyph
        strings are split into individual characters. The corpus is the only
        source of truth for what can be traced, so call this before finalizing
        the pack. Returns each found hanzi with its stroke count (a difficulty
        signal) and the candidates that are absent, so you can drop or replace
        them. The corpus has no pinyin or meanings — supply those yourself.
        """
        return await find_characters(ctx.deps, candidates)

    @agent.output_validator
    async def _validate(ctx: RunContext[GenerationDeps], draft: PackDraft) -> PackDraft:
        return await validate_corpus_membership(ctx.deps, draft)

    return agent


# Built once at import time; safe because no model is bound (no network, no
# configuration required). Routers depend on it via ``get_generation_agent``.
_generation_agent = _build_generation_agent()


def get_generation_agent() -> Agent[GenerationDeps, PackDraft]:
    """FastAPI dependency returning the shared generation agent.

    Trivial and argument-free so integration/e2e tests can swap it wholesale via
    ``app.dependency_overrides[get_generation_agent]``.
    """
    return _generation_agent


def _build_model() -> OpenAIChatModel:
    """Return the OpenRouter-backed model for a generation run.

    Lazy and gated: only built when generation is configured, then cached for
    reuse by the shared :mod:`habagou.services.openrouter` builder.
    """
    if not settings.generation_configured:
        raise GenerationNotConfiguredError(
            "Pack generation is not configured: set OPENROUTER_API_KEY (and "
            "GENERATION_MODEL) to enable it."
        )
    return build_openrouter_model(settings.generation_model)


async def generate_pack_draft(
    agent: Agent[GenerationDeps, PackDraft],
    *,
    session: AsyncSession,
    topic: str,
    history: list[ModelMessage] | None = None,
) -> GenerationResult:
    """Run the agent to draft a pack for ``topic`` and return draft + history.

    Assembles :class:`GenerationDeps` around a real ``CharacterRepository`` bound
    to ``session``, supplies the OpenRouter model at call time, and threads prior
    ``history`` so refinement turns keep context (HAB-082). Returns the validated
    :class:`~habagou.dtos.generation.PackDraft` alongside the full updated message
    history for the caller to persist.
    """
    deps = GenerationDeps(characters=CharacterRepository(session))
    logger = structlog.get_logger("habagou.generation")
    # An empty client-held history is a fresh first turn (pydantic-ai treats []
    # like None), so only a non-empty history counts as a refinement.
    refinement = bool(history)
    started_at = time.monotonic()
    try:
        result = await agent.run(
            topic,
            deps=deps,
            model=_build_model(),
            message_history=history,
        )
    except Exception:
        # The worst latency cases (retry exhaustion, provider errors) raise here;
        # log them too so they are not invisible to the round-trip metric.
        logger.warning(
            "generation_run_failed",
            duration_ms=round((time.monotonic() - started_at) * 1000),
            refinement=refinement,
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
