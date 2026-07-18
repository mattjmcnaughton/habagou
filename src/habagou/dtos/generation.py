"""DTOs for agent pack generation (Epic 7).

``PackDraft`` is the agent's ``output_type``: a structured, validated draft the
model produces from the stroke corpus. The pinyin/meaning/translation glosses
are model-generated — the corpus itself stores no such data. Field names are
kept identical to the persisted pack shape (``hanzi``/``pinyin``/``meaning`` for
characters, ``hanzi``/``pinyin``/``translation`` for sentences — see
:class:`habagou.repositories.packs.PackSentenceInput`) so a draft maps onto the
save path without renaming.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, Field

# ChatModelOptionDTO annotates pydantic model fields, which pydantic resolves
# at runtime, so it is imported eagerly (not TYPE_CHECKING).
from habagou.dtos.chat_models import ChatModelOptionDTO  # noqa: TC001

# Size bounds keep hand-crafted payloads from amplifying into oversized
# database writes or oversized (billed) model calls, while staying generous
# enough that a well-behaved model never trips them into a needless retry.
GlossStr = Annotated[str, Field(min_length=1, max_length=200)]
SentenceHanziStr = Annotated[str, Field(min_length=1, max_length=64)]
SentenceGlossStr = Annotated[str, Field(min_length=1, max_length=512)]


class PackDraftCharacter(BaseModel):
    """A single drafted character with its model-generated gloss."""

    hanzi: Annotated[str, Field(min_length=1, max_length=1)]
    pinyin: GlossStr
    meaning: GlossStr


class PackDraftSentence(BaseModel):
    """A drafted example sentence for the sentence-tracing activity."""

    hanzi: SentenceHanziStr
    pinyin: SentenceGlossStr
    translation: SentenceGlossStr


class PackDraft(BaseModel):
    """Structured output the generation agent returns for a practice pack."""

    title: Annotated[str, Field(min_length=1, max_length=120)]
    characters: Annotated[list[PackDraftCharacter], Field(min_length=1, max_length=30)]
    sentences: Annotated[list[PackDraftSentence], Field(max_length=12)] = Field(
        default_factory=list
    )
    coverage_note: Annotated[str, Field(min_length=1, max_length=1000)] | None = None


class GenerationDraftRequestDTO(BaseModel):
    """Request to draft (or refine) a pack from a topic.

    ``history`` is the opaque JSON message history returned by a prior draft
    turn (see :class:`GenerationDraftResponseDTO`); replaying it lets a
    refinement turn keep the model's context. It is ``None`` on the first turn.
    """

    topic: Annotated[str, Field(min_length=1, max_length=2000)]
    history: Annotated[list[Any], Field(max_length=200)] | None = None
    # Admin-only OpenRouter model override; must be one of the server's
    # selectable generation model ids (``Settings.generation_model_ids``).
    # ``None`` runs the server default. Non-admins sending a model get a 403.
    model: Annotated[str, Field(min_length=1, max_length=200)] | None = None


class GenerationDraftResponseDTO(BaseModel):
    """A drafted pack plus the updated conversation history to persist.

    The client holds ``history`` between turns and passes it back on the next
    :class:`GenerationDraftRequestDTO` to refine the draft.
    """

    draft: PackDraft
    history: list[Any]


class GenerationSavePackRequestDTO(BaseModel):
    """Request to persist a finalized :class:`PackDraft` as an owned pack."""

    draft: PackDraft


class GenerationStatusDTO(BaseModel):
    """Whether agent pack generation is available, for entry-point gating.

    The frontend calls this before deciding whether to surface the "Create a
    pack" entry point (issue #102 / mockup): when generation is unconfigured the
    button stays hidden, so a user is never offered a flow that can only 503.
    ``enabled`` mirrors :attr:`habagou.config.Settings.generation_configured`
    (True only when both the OpenRouter key and the model are set); it is not a
    per-user capability, just a server-wide readiness flag.

    ``models`` and ``default_model`` are the admin model picker's data: the
    selectable OpenRouter models (default first) and the id that runs when the
    request carries no override. Both are ``None`` for non-admin callers — the
    response itself gates the picker UI — and when generation is unconfigured.
    """

    enabled: bool
    models: list[ChatModelOptionDTO] | None = None
    default_model: str | None = None
