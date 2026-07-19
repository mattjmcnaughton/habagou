"""Validate curated pack data files without a database.

Checks ``data/packs/categories.json`` and every ``data/packs/<category>/
<slug>.json`` against the schema and cross-file invariants, including corpus
membership of every traced glyph via the committed ``data/corpus_index.txt``
(regenerate with ``scripts/import_stroke_data.py --write-index``). Runs in
``just gate`` / CI; exits non-zero listing every violation.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data" / "packs"
CORPUS_INDEX = REPO_ROOT / "data" / "corpus_index.txt"

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
COLOR_PATTERN = re.compile(r"^#[0-9a-f]{6}$")

MIN_CHARACTERS = 4
MAX_CHARACTERS = 10
MIN_SENTENCES = 2
MAX_SENTENCES = 5

# Owned (user/AI-created) packs sort at 1_000_000 (services/pack_generation.py)
# so they always follow curated content on the bench; curated sort_orders must
# stay well below that ceiling.
MAX_SORT_ORDER = 99_999


class CategoryFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str
    title: str
    sort_order: int


class PackCharacterFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hanzi: str
    pinyin: str
    meaning: str


class PackSentenceFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hanzi: str
    pinyin: str
    translation: str


class PackFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str
    title: str
    glyph: str
    color: str
    category: str
    description: str
    starter: bool
    sort_order: int
    characters: list[PackCharacterFile]
    sentences: list[PackSentenceFile]


def load_corpus(path: Path = CORPUS_INDEX) -> set[str]:
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def validate_categories(path: Path, errors: list[str]) -> dict[str, CategoryFile]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        entries = [CategoryFile.model_validate(entry) for entry in raw]
    except (json.JSONDecodeError, ValidationError) as error:
        errors.append(f"{path}: {error}")
        return {}

    categories: dict[str, CategoryFile] = {}
    orders: dict[int, str] = {}
    for entry in entries:
        if not SLUG_PATTERN.match(entry.slug):
            errors.append(f"{path}: category slug {entry.slug!r} is not kebab-case")
        if not entry.title.strip():
            errors.append(f"{path}: category {entry.slug!r} has an empty title")
        if entry.slug in categories:
            errors.append(f"{path}: duplicate category slug {entry.slug!r}")
        if entry.sort_order in orders:
            errors.append(
                f"{path}: category sort_order {entry.sort_order} duplicated by "
                f"{entry.slug!r} and {orders[entry.sort_order]!r}"
            )
        categories[entry.slug] = entry
        orders.setdefault(entry.sort_order, entry.slug)
    return categories


def validate_pack(
    path: Path,
    pack: PackFile,
    categories: dict[str, CategoryFile],
    corpus: set[str],
    errors: list[str],
) -> None:
    if not SLUG_PATTERN.match(pack.slug):
        errors.append(f"{path}: slug {pack.slug!r} is not kebab-case")
    if path.stem != pack.slug:
        errors.append(f"{path}: filename does not match slug {pack.slug!r}")
    if path.parent.name != pack.category:
        errors.append(
            f"{path}: directory {path.parent.name!r} does not match "
            f"category {pack.category!r}"
        )
    if pack.category not in categories:
        errors.append(f"{path}: unknown category {pack.category!r}")
    if not 0 < pack.sort_order <= MAX_SORT_ORDER:
        errors.append(
            f"{path}: sort_order {pack.sort_order} outside 1-{MAX_SORT_ORDER}"
        )
    if not COLOR_PATTERN.match(pack.color):
        errors.append(f"{path}: color {pack.color!r} is not lowercase #rrggbb")
    if not pack.title.strip():
        errors.append(f"{path}: empty title")
    if not pack.description.strip():
        errors.append(f"{path}: empty description")

    if not MIN_CHARACTERS <= len(pack.characters) <= MAX_CHARACTERS:
        errors.append(
            f"{path}: {len(pack.characters)} characters (want "
            f"{MIN_CHARACTERS}-{MAX_CHARACTERS})"
        )
    if not MIN_SENTENCES <= len(pack.sentences) <= MAX_SENTENCES:
        errors.append(
            f"{path}: {len(pack.sentences)} sentences (want "
            f"{MIN_SENTENCES}-{MAX_SENTENCES})"
        )

    member_hanzi = [character.hanzi for character in pack.characters]
    if len(set(member_hanzi)) != len(member_hanzi):
        errors.append(f"{path}: duplicate member characters")
    if pack.glyph not in member_hanzi:
        errors.append(f"{path}: glyph {pack.glyph!r} is not a member character")

    for character in pack.characters:
        if len(character.hanzi) != 1:
            errors.append(f"{path}: member {character.hanzi!r} is not a single glyph")
        elif character.hanzi not in corpus:
            errors.append(f"{path}: member {character.hanzi!r} missing from corpus")
        if not character.pinyin.strip() or not character.meaning.strip():
            errors.append(
                f"{path}: member {character.hanzi!r} has empty pinyin/meaning"
            )

    for sentence in pack.sentences:
        glyphs = [glyph for glyph in sentence.hanzi if glyph.strip()]
        if not glyphs:
            errors.append(f"{path}: empty sentence")
            continue
        # Every sentence glyph is traced, so all of them (punctuation
        # included, which the corpus lacks) must be corpus members.
        missing = [glyph for glyph in glyphs if glyph not in corpus]
        if missing:
            errors.append(
                f"{path}: sentence {sentence.hanzi!r} uses non-corpus "
                f"glyphs {''.join(missing)!r}"
            )
        if not sentence.pinyin.strip() or not sentence.translation.strip():
            errors.append(
                f"{path}: sentence {sentence.hanzi!r} has empty pinyin/translation"
            )


def validate(data_dir: Path = DATA_DIR, corpus_index: Path = CORPUS_INDEX) -> list[str]:
    errors: list[str] = []
    corpus = load_corpus(corpus_index)
    categories = validate_categories(data_dir / "categories.json", errors)

    slugs: dict[str, Path] = {}
    orders: dict[int, str] = {}
    pack_files = sorted(data_dir.glob("*/*.json"))
    if not pack_files:
        errors.append(f"{data_dir}: no pack files found")

    for path in pack_files:
        try:
            pack = PackFile.model_validate_json(path.read_text(encoding="utf-8"))
        except ValidationError as error:
            errors.append(f"{path}: {error}")
            continue

        if pack.slug in slugs:
            errors.append(
                f"{path}: slug {pack.slug!r} already used by {slugs[pack.slug]}"
            )
        slugs.setdefault(pack.slug, path)
        if pack.sort_order in orders:
            errors.append(
                f"{path}: sort_order {pack.sort_order} duplicated by "
                f"{pack.slug!r} and {orders[pack.sort_order]!r}"
            )
        orders.setdefault(pack.sort_order, pack.slug)

        validate_pack(path, pack, categories, corpus, errors)

    return errors


def main() -> None:
    errors = validate()
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        print(f"pack data validation failed: {len(errors)} error(s)", file=sys.stderr)
        raise SystemExit(1)
    pack_count = len(list(DATA_DIR.glob("*/*.json")))
    print(f"pack data validation passed: {pack_count} packs")


if __name__ == "__main__":
    main()
