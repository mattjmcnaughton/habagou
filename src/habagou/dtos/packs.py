"""DTOs for pack API responses."""

from __future__ import annotations

import uuid  # noqa: TC003 - Pydantic resolves UUID annotations at runtime.

from pydantic import BaseModel


class ActivityProgressDTO(BaseModel):
    completed: bool
    completion_count: int
    best_duration_ms: int | None


class PackProgressDTO(BaseModel):
    trace: ActivityProgressDTO
    match: ActivityProgressDTO
    sentence: ActivityProgressDTO


class PackSummaryDTO(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    glyph: str
    color: str
    char_count: int
    sentence_count: int
    progress: PackProgressDTO


class PackCharacterDTO(BaseModel):
    hanzi: str
    pinyin: str
    meaning: str


class PackSentenceDTO(BaseModel):
    hanzi: str
    pinyin: str
    translation: str


class PackDetailDTO(PackSummaryDTO):
    characters: list[PackCharacterDTO]
    sentences: list[PackSentenceDTO]
