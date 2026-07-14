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

from typing import Annotated

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
