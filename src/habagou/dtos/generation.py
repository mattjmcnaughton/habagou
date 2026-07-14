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

NonEmptyStr = Annotated[str, Field(min_length=1)]


class PackDraftCharacter(BaseModel):
    """A single drafted character with its model-generated gloss."""

    hanzi: Annotated[str, Field(min_length=1, max_length=1)]
    pinyin: NonEmptyStr
    meaning: NonEmptyStr


class PackDraftSentence(BaseModel):
    """A drafted example sentence for the sentence-tracing activity."""

    hanzi: NonEmptyStr
    pinyin: NonEmptyStr
    translation: NonEmptyStr


class PackDraft(BaseModel):
    """Structured output the generation agent returns for a practice pack."""

    title: NonEmptyStr
    characters: Annotated[list[PackDraftCharacter], Field(min_length=1)]
    sentences: list[PackDraftSentence] = Field(default_factory=list)
    coverage_note: NonEmptyStr | None = None


class GenerationDraftRequestDTO(BaseModel):
    """Request to draft (or refine) a pack from a topic.

    ``history`` is the opaque JSON message history returned by a prior draft
    turn (see :class:`GenerationDraftResponseDTO`); replaying it lets a
    refinement turn keep the model's context. It is ``None`` on the first turn.
    """

    topic: NonEmptyStr
    history: list[Any] | None = None


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
