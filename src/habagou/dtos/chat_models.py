"""Shared DTO for the admin AI-model picker.

Both AI chat features (pack generation and conversational practice) surface
their selectable OpenRouter models to admins through their status endpoints;
this option shape is common to both.
"""

from __future__ import annotations

from pydantic import BaseModel


class ChatModelOptionDTO(BaseModel):
    """One selectable model: the OpenRouter id plus a display label."""

    id: str
    label: str
