from __future__ import annotations

from habagou.graphemes import is_single_grapheme


def test_is_single_grapheme_accepts_one_character() -> None:
    assert is_single_grapheme("你") is True


def test_is_single_grapheme_rejects_empty_or_multiple_characters() -> None:
    assert is_single_grapheme("") is False
    assert is_single_grapheme("你好") is False
