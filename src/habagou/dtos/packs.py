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
    title: str
    glyph: str
    color: str
    char_count: int
    sentence_count: int
    # True when the current user owns this pack (a private pack they can
    # delete); False for global, curated packs visible to everyone.
    owned: bool
    # Library catalog flag: enabled by default for every user.
    starter: bool
    # Effective enablement for the current user. Always True on the bench
    # (owned packs and enabled global packs); False only when a global pack
    # is previewed from the library without being enabled.
    enabled: bool
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


class PackEnablementUpdateDTO(BaseModel):
    enabled: bool


class LibraryPackDTO(BaseModel):
    """Slim library card: no progress aggregates (the library lists hundreds
    of packs; per-pack progress stays a bench concern)."""

    id: uuid.UUID
    title: str
    glyph: str
    color: str
    description: str | None
    char_count: int
    sentence_count: int
    starter: bool
    enabled: bool


class LibraryCategoryDTO(BaseModel):
    slug: str
    title: str
    packs: list[LibraryPackDTO]


class LibraryDTO(BaseModel):
    categories: list[LibraryCategoryDTO]
