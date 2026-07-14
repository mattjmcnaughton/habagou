"""Unit tests for the PackDraft agent output schema (HAB-078)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from habagou.dtos.generation import (
    PackDraft,
    PackDraftCharacter,
    PackDraftSentence,
)


def _valid_draft_kwargs() -> dict:
    return {
        "title": "Greetings",
        "characters": [
            {"hanzi": "你", "pinyin": "nǐ", "meaning": "you"},
            {"hanzi": "好", "pinyin": "hǎo", "meaning": "good"},
        ],
        "sentences": [
            {"hanzi": "你好", "pinyin": "nǐ hǎo", "translation": "hello"},
        ],
        "coverage_note": "found 2 of 2 requested characters",
    }


def test_well_formed_draft_validates() -> None:
    draft = PackDraft.model_validate(_valid_draft_kwargs())
    assert draft.title == "Greetings"
    assert len(draft.characters) == 2
    assert draft.sentences[0].translation == "hello"
    assert draft.coverage_note is not None


def test_sentences_default_empty_and_coverage_note_optional() -> None:
    draft = PackDraft(
        title="Solo",
        characters=[PackDraftCharacter(hanzi="人", pinyin="rén", meaning="person")],
    )
    assert draft.sentences == []
    assert draft.coverage_note is None


def test_empty_title_rejected() -> None:
    kwargs = _valid_draft_kwargs()
    kwargs["title"] = ""
    with pytest.raises(ValidationError):
        PackDraft.model_validate(kwargs)


def test_no_characters_rejected() -> None:
    kwargs = _valid_draft_kwargs()
    kwargs["characters"] = []
    with pytest.raises(ValidationError):
        PackDraft.model_validate(kwargs)


def test_multi_char_hanzi_rejected() -> None:
    with pytest.raises(ValidationError):
        PackDraftCharacter(hanzi="你好", pinyin="nǐ hǎo", meaning="hello")


def test_empty_character_field_rejected() -> None:
    with pytest.raises(ValidationError):
        PackDraftCharacter(hanzi="你", pinyin="", meaning="you")


def test_missing_character_field_rejected() -> None:
    with pytest.raises(ValidationError):
        PackDraftCharacter.model_validate({"hanzi": "你", "pinyin": "nǐ"})


def test_sentence_requires_translation_not_meaning() -> None:
    # Field is ``translation`` (aligned with PackSentenceInput), not ``meaning``.
    assert "translation" in PackDraftSentence.model_fields
    assert "meaning" not in PackDraftSentence.model_fields
    with pytest.raises(ValidationError):
        PackDraftSentence(hanzi="你好", pinyin="nǐ hǎo", translation="")
