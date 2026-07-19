"""Unit tests for the pack response DTO contract."""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from habagou.dtos.packs import (
    ActivityProgressDTO,
    PackDetailDTO,
    PackProgressDTO,
    PackSummaryDTO,
)


def _progress() -> PackProgressDTO:
    activity = ActivityProgressDTO(
        completed=False, completion_count=0, best_duration_ms=None
    )
    return PackProgressDTO(trace=activity, match=activity, sentence=activity)


def _summary_kwargs() -> dict:
    return {
        "id": uuid.uuid4(),
        "title": "Greetings",
        "glyph": "你",
        "color": "#c4633f",
        "char_count": 5,
        "sentence_count": 3,
        "owned": True,
        "starter": False,
        "enabled": True,
        "progress": _progress(),
    }


def test_summary_exposes_owned_flag() -> None:
    summary = PackSummaryDTO(**_summary_kwargs())
    assert summary.owned is True


def test_owned_is_required() -> None:
    kwargs = _summary_kwargs()
    del kwargs["owned"]
    with pytest.raises(ValidationError):
        PackSummaryDTO(**kwargs)


def test_detail_inherits_owned_flag() -> None:
    detail = PackDetailDTO(**_summary_kwargs(), characters=[], sentences=[])
    assert detail.owned is True
