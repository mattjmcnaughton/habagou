"""Shared admin model-selection helpers for the AI chat routers.

Pack generation and conversational practice expose the same admin capability:
their status endpoints list the selectable OpenRouter models, and their run
endpoints accept an optional per-request model override. These helpers keep
the gating rules identical across the two routers:

- options are returned only to admins, and only when the feature is
  configured (a picker for a 503-ing feature would be noise);
- an override from a non-admin is a 403 (the capability is admin-only — the
  hidden picker is cosmetic, this is the real gate);
- an override outside the feature's allowlist is a 422 naming the allowed ids.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException, status

from habagou.authz import is_admin
from habagou.dtos.chat_models import ChatModelOptionDTO
from habagou.services.openrouter import model_label

if TYPE_CHECKING:
    from habagou.models import User


def admin_model_options(
    user: User, *, configured: bool, model_ids: tuple[str, ...]
) -> list[ChatModelOptionDTO] | None:
    """The status endpoint's picker options, or ``None`` when not applicable."""
    if not configured or not is_admin(user):
        return None
    return [
        ChatModelOptionDTO(id=model_id, label=model_label(model_id))
        for model_id in model_ids
    ]


def resolve_model_override(
    model: str | None, *, user: User, allowed: tuple[str, ...]
) -> str | None:
    """Validate a requested model override; return it (or ``None``) if legal."""
    if model is None:
        return None
    if not is_admin(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="model selection requires an admin account",
        )
    if model not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"model must be one of: {', '.join(allowed)}",
        )
    return model
