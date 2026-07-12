"""DTOs for learning Path API requests and responses."""

from __future__ import annotations

import uuid  # noqa: TC003 - Pydantic resolves UUID annotations at runtime.
from typing import Any, Literal

from pydantic import BaseModel, Field, model_serializer


class PathCharDTO(BaseModel):
    hanzi: str
    pinyin: str
    meaning: str


class PathTraceContentDTO(BaseModel):
    chars: list[PathCharDTO]


class PathMatchContentDTO(BaseModel):
    pairs: list[PathCharDTO]


class PathSentenceContentDTO(BaseModel):
    hanzi: str
    pinyin: str
    translation: str


class PathContentDTO(BaseModel):
    """Item content carrying exactly one key matching the item's activity.

    Exactly one of the three fields is populated; serialization emits only that
    key so the wire shape is ``{"trace": {...}}`` / ``{"match": {...}}`` /
    ``{"sentence": {...}}``.
    """

    trace: PathTraceContentDTO | None = None
    match: PathMatchContentDTO | None = None
    sentence: PathSentenceContentDTO | None = None

    @model_serializer
    def _serialize_single_key(self) -> dict[str, Any]:
        for key in ("trace", "match", "sentence"):
            value = getattr(self, key)
            if value is not None:
                return {key: value.model_dump()}
        return {}


class PathPackDTO(BaseModel):
    slug: str
    title: str
    glyph: str
    color: str


class PathItemDTO(BaseModel):
    id: uuid.UUID
    position: int
    activity: Literal["trace", "match", "sentence"]
    kind: Literal["new", "review"]
    state: Literal["done", "current", "locked"]
    unit_label: str | None
    pack: PathPackDTO
    content: PathContentDTO


class PathDailyDTO(BaseModel):
    completed: int
    target: int


class PathDueDTO(BaseModel):
    new: int
    review: int


class PathResponseDTO(BaseModel):
    items: list[PathItemDTO]
    next_cursor: int | None
    daily: PathDailyDTO
    streak: int
    due: PathDueDTO


class PathItemCompleteDTO(BaseModel):
    duration_ms: int = Field(ge=0)


class PathItemCompleteResponseDTO(BaseModel):
    daily: PathDailyDTO
    streak: int
    item_id: uuid.UUID
    next_item_id: uuid.UUID | None
