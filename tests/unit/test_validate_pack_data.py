"""Unit tests for the pack data validator (no database, no network)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from scripts.validate_pack_data import validate

if TYPE_CHECKING:
    from pathlib import Path


def _pack(**overrides: Any) -> dict[str, Any]:
    pack: dict[str, Any] = {
        "slug": "greetings",
        "title": "Greetings",
        "glyph": "你",
        "color": "#c4633f",
        "category": "basics",
        "description": "Say hello.",
        "starter": True,
        "sort_order": 1,
        "characters": [
            {"hanzi": "你", "pinyin": "nǐ", "meaning": "you"},
            {"hanzi": "好", "pinyin": "hǎo", "meaning": "good"},
            {"hanzi": "我", "pinyin": "wǒ", "meaning": "I"},
            {"hanzi": "他", "pinyin": "tā", "meaning": "he"},
        ],
        "sentences": [
            {"hanzi": "你好", "pinyin": "nǐ hǎo", "translation": "Hello"},
            {"hanzi": "我好", "pinyin": "wǒ hǎo", "translation": "I am well"},
        ],
    }
    pack.update(overrides)
    return pack


def _write_data(
    tmp_path: Path,
    packs: list[dict[str, Any]],
    *,
    corpus: str = "你\n好\n我\n他\n",
) -> tuple[Path, Path]:
    data_dir = tmp_path / "packs"
    data_dir.mkdir()
    (data_dir / "categories.json").write_text(
        json.dumps([{"slug": "basics", "title": "Basics", "sort_order": 1}]),
        encoding="utf-8",
    )
    for pack in packs:
        category_dir = data_dir / pack["category"]
        category_dir.mkdir(exist_ok=True)
        (category_dir / f"{pack['slug']}.json").write_text(
            json.dumps(pack), encoding="utf-8"
        )
    corpus_index = tmp_path / "corpus_index.txt"
    corpus_index.write_text(corpus, encoding="utf-8")
    return data_dir, corpus_index


def test_valid_pack_data_passes(tmp_path: Path) -> None:
    data_dir, corpus_index = _write_data(tmp_path, [_pack()])
    assert validate(data_dir, corpus_index) == []


def test_non_corpus_member_and_sentence_glyphs_are_reported(tmp_path: Path) -> None:
    pack = _pack(
        characters=[
            {"hanzi": "你", "pinyin": "nǐ", "meaning": "you"},
            {"hanzi": "好", "pinyin": "hǎo", "meaning": "good"},
            {"hanzi": "我", "pinyin": "wǒ", "meaning": "I"},
            {"hanzi": "猫", "pinyin": "māo", "meaning": "cat"},
        ],
        sentences=[
            {"hanzi": "你好", "pinyin": "nǐ hǎo", "translation": "Hello"},
            {"hanzi": "狗好", "pinyin": "gǒu hǎo", "translation": "Dog is well"},
        ],
    )
    data_dir, corpus_index = _write_data(tmp_path, [pack])
    errors = validate(data_dir, corpus_index)
    assert any("猫" in error and "missing from corpus" in error for error in errors)
    assert any("狗" in error and "non-corpus" in error for error in errors)


def test_duplicate_slug_and_sort_order_are_reported(tmp_path: Path) -> None:
    first = _pack()
    second = _pack(title="Copy")
    data_dir, corpus_index = _write_data(tmp_path, [first])
    # Same slug in a second file (different name so both files exist).
    (data_dir / "basics" / "copy.json").write_text(json.dumps(second), encoding="utf-8")
    errors = validate(data_dir, corpus_index)
    assert any("already used" in error for error in errors)
    assert any("does not match slug" in error for error in errors)


def test_unknown_category_and_bad_color_are_reported(tmp_path: Path) -> None:
    pack = _pack(category="mystery", color="#ZZZZZZ")
    data_dir, corpus_index = _write_data(tmp_path, [pack])
    errors = validate(data_dir, corpus_index)
    assert any("unknown category 'mystery'" in error for error in errors)
    assert any("not lowercase #rrggbb" in error for error in errors)


def test_glyph_must_be_a_member_and_counts_bounded(tmp_path: Path) -> None:
    pack = _pack(
        glyph="好",
        characters=[{"hanzi": "你", "pinyin": "nǐ", "meaning": "you"}],
        sentences=[{"hanzi": "你好", "pinyin": "nǐ hǎo", "translation": "Hello"}],
    )
    data_dir, corpus_index = _write_data(tmp_path, [pack])
    errors = validate(data_dir, corpus_index)
    assert any("is not a member character" in error for error in errors)
    assert any("1 characters" in error for error in errors)
    assert any("1 sentences" in error for error in errors)


def test_committed_pack_data_is_valid() -> None:
    """The real data/packs tree must always pass (the gate runs this)."""
    assert validate() == []
