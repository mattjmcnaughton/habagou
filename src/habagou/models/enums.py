"""Shared enums for the ORM models."""

from __future__ import annotations

from enum import StrEnum


class ActivityType(StrEnum):
    """Activity variants that can create completion events."""

    TRACE = "trace"
    MATCH = "match"
    SENTENCE = "sentence"


class PathItemKind(StrEnum):
    """Whether a path item introduces new material or resurfaces due units."""

    NEW = "new"
    REVIEW = "review"


class ReviewUnitType(StrEnum):
    """The kind of reviewable unit tracked by a review state row."""

    CHARACTER = "character"
    SENTENCE = "sentence"


class CompletionSource(StrEnum):
    """Origin of a completion event: a whole-pack activity or a path item."""

    PACK = "pack"
    PATH = "path"
