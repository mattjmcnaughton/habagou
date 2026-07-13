"""SQLAlchemy ORM models.

One module per bounded context, with shared enums in :mod:`.enums`. All models
are imported here so ``Base.metadata`` sees every table and SQLAlchemy can
resolve cross-module relationship references through its class registry. Call
sites keep importing ``from habagou.models import X``.
"""

from __future__ import annotations

from habagou.models.characters import Character
from habagou.models.enums import (
    ActivityType,
    CompletionSource,
    PathItemKind,
    ReviewUnitType,
)
from habagou.models.packs import Pack, PackCharacter, PackSentence
from habagou.models.path import PathItem
from habagou.models.progress import ActivityCompletion
from habagou.models.review import ReviewState
from habagou.models.users import User

__all__ = [
    "ActivityCompletion",
    "ActivityType",
    "Character",
    "CompletionSource",
    "Pack",
    "PackCharacter",
    "PackSentence",
    "PathItem",
    "PathItemKind",
    "ReviewState",
    "ReviewUnitType",
    "User",
]
