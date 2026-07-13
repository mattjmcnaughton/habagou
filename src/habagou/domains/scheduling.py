"""Pure spaced-repetition scheduling for the learning Path.

No I/O, no ORM, no side effects: data in, data out, fully deterministic. The
service layer (BE-3) maps ORM rows onto the plain dataclasses defined here and
maps the resulting :class:`ItemSpec` list back into ``path_items`` rows.

Scheduler v1 is a fixed Leitner ladder with a binary completion signal (no ease
factor). :data:`LADDER` holds the interval, in days, after each successful rep.

Reviewable units (see ``CONTEXT.md``, binding glossary)
-------------------------------------------------------
Spaced repetition tracks and schedules a *reviewable unit* per learner and per
activity, identified here by ``(pack_slug, unit_type, unit_ref, activity)``:

* Trace and Match track **one pack character each**, with *separate* strengths
  (a character has an independent ``trace`` unit and ``match`` unit).
* Sentence tracks the **whole sentence** as one unit; its constituent
  characters are never individually scheduled. Characters that appear in a
  sentence but not in the pack's character list are traced on screen but never
  become reviewable units, so the scheduler never sees them.

Seen / new / due
----------------
A unit is **introduced** (a.k.a. *seen*) exactly when a :class:`ReviewState`
exists for it. **New** material is any curriculum unit *without* a review state.
A unit is **due** when its review state has ``due_at`` set and ``due_at <= now``.
A review state may carry ``reps == 0`` / ``due_at is None`` to mean
"introduced but not yet practiced" -- such a unit is neither new nor due, which
lets the caller record a unit as introduced at generation time so subsequent
:func:`generate_batch` calls advance through the curriculum rather than
re-emitting the same new material.

Generation batch (decision 6)
-----------------------------
:func:`generate_batch` returns one *batch* (a coherent, bounded chunk):

1. **Due reviews first**, oldest ``due_at`` first. Due units of the same
   ``(pack, activity)`` are grouped into one item -- trace 2-3 chars, match 3-5
   pairs, sentence one sentence.
2. Then **new material** in deterministic curriculum order: packs in the order
   they appear in :class:`Curriculum` (the caller sorts by ``sort_order``),
   within a pack in character/sentence order (the caller sorts by ``position``):
   trace items (2-3 chars each) first, then match item(s) over the pack's
   recently introduced characters (3-5 pairs), then the pack's sentences one
   item each.
3. On **exhaustion** (nothing new, nothing due) the soonest-due introduced units
   resurface as early-review items -- the Path never ends, so
   :func:`generate_batch` never returns an empty list when the curriculum is
   non-empty.

Every :class:`ItemSpec` is ``kind='new'`` (introduces at least one unseen unit)
or ``kind='review'`` (resurfaces already-seen units).

Unit labels (decision 5)
------------------------
Path "units" are a cosmetic grouping over consecutive items; only the first item
of a batch carries a ``unit_label`` (the rest are ``None``). The scheme is
deterministic: the number is derived from how many reviewable units the learner
has already been introduced to (``len(review_states) // UNIT_STRIDE``) and the
phrase cycles through :data:`UNIT_PHRASES`, so a brand-new learner's first batch
is labelled ``"UNIT 1 · WARMING UP"``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import timedelta
from math import ceil
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from datetime import datetime

Activity = Literal["trace", "match", "sentence"]
UnitType = Literal["character", "sentence"]
Kind = Literal["new", "review"]

#: Leitner intervals in days; index i is the wait after the (i+1)-th rep.
LADDER: tuple[int, ...] = (1, 3, 7, 14, 30)

#: Default number of items in one generated batch.
DEFAULT_BATCH_SIZE = 5

TRACE_MAX = 3
MATCH_MAX = 5
#: A match item needs at least this many characters to pair against.
MATCH_MIN = 2

#: Cosmetic unit phrases, cycled through as the learner progresses.
UNIT_PHRASES: tuple[str, ...] = (
    "WARMING UP",
    "FINDING RHYTHM",
    "BUILDING BLOCKS",
    "STEADY HANDS",
    "DEEPER WATERS",
    "MASTERY",
)
#: Reviewable units introduced per unit-label increment.
UNIT_STRIDE = 6


# --------------------------------------------------------------------------- #
# Curriculum inputs (plain data; the service maps ORM rows onto these).
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CharacterSpec:
    """One pack character, in ``position`` order within its pack."""

    hanzi: str
    pinyin: str
    meaning: str


@dataclass(frozen=True)
class SentenceSpec:
    """One pack sentence. ``ref`` is a stable per-pack identity for the unit."""

    ref: str
    hanzi: str
    pinyin: str
    translation: str


@dataclass(frozen=True)
class PackSpec:
    """A pack's curriculum slice. ``characters`` / ``sentences`` are ordered."""

    slug: str
    title: str
    glyph: str
    color: str
    characters: tuple[CharacterSpec, ...] = ()
    sentences: tuple[SentenceSpec, ...] = ()


@dataclass(frozen=True)
class Curriculum:
    """All packs in curriculum order (caller sorts by ``sort_order``)."""

    packs: tuple[PackSpec, ...] = ()


# --------------------------------------------------------------------------- #
# Review-state inputs / outputs.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ReviewUnit:
    """Identity of a reviewable unit, per learner and per activity."""

    pack_slug: str
    unit_type: UnitType
    unit_ref: str
    activity: Activity


@dataclass(frozen=True)
class ReviewState:
    """Scheduling state for one reviewable unit.

    ``reps == 0`` with ``due_at is None`` means "introduced, not yet practiced".
    """

    pack_slug: str
    unit_type: UnitType
    unit_ref: str
    activity: Activity
    reps: int = 0
    last_seen_at: datetime | None = None
    due_at: datetime | None = None

    @property
    def unit(self) -> ReviewUnit:
        return ReviewUnit(self.pack_slug, self.unit_type, self.unit_ref, self.activity)


@dataclass(frozen=True)
class PackRef:
    """The pack fields an item snapshot needs to render its badge."""

    slug: str
    title: str
    glyph: str
    color: str


@dataclass(frozen=True)
class ItemSpec:
    """One generated path item.

    ``content`` is the pinned snapshot BE-3 maps to the API ``content`` shape:

    * trace -- ``{"chars": [{"hanzi", "pinyin", "meaning"}, ...]}``
    * match -- ``{"pairs": [{"hanzi", "pinyin", "meaning"}, ...]}``
    * sentence -- ``{"hanzi", "pinyin", "translation"}``

    ``units`` lists the reviewable units the item touches, so the service can
    apply the ladder to each on completion.
    """

    activity: Activity
    kind: Kind
    pack: PackRef
    content: dict[str, Any]
    units: tuple[ReviewUnit, ...]
    unit_label: str | None = None


def apply_completion(state: ReviewState, completed_at: datetime) -> ReviewState:
    """Advance a reviewable unit one rung up the ladder.

    ``reps += 1``; ``due_at = completed_at + LADDER[min(reps - 1, len - 1)]``
    days (clamped at the top rung); ``last_seen_at = completed_at``.
    """
    reps = state.reps + 1
    interval_days = LADDER[min(reps - 1, len(LADDER) - 1)]
    return replace(
        state,
        reps=reps,
        due_at=completed_at + timedelta(days=interval_days),
        last_seen_at=completed_at,
    )


def generate_batch(
    curriculum: Curriculum,
    review_states: Iterable[ReviewState],
    now: datetime,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> list[ItemSpec]:
    """Generate one batch of path items (see the module docstring).

    Deterministic: identical inputs yield an identical batch. Never returns an
    empty list when the curriculum is non-empty.
    """
    states = list(review_states)
    states_by_key = {_state_key(s): s for s in states}
    pack_order = {p.slug: i for i, p in enumerate(curriculum.packs)}
    pack_by_slug = {p.slug: p for p in curriculum.packs}
    char_by_key: dict[tuple[str, str], tuple[PackSpec, CharacterSpec]] = {}
    sent_by_key: dict[tuple[str, str], tuple[PackSpec, SentenceSpec]] = {}
    position_by_key: dict[tuple[str, str, str], int] = {}
    for pack in curriculum.packs:
        for index, char in enumerate(pack.characters):
            char_by_key[(pack.slug, char.hanzi)] = (pack, char)
            position_by_key[(pack.slug, "character", char.hanzi)] = index
        for index, sentence in enumerate(pack.sentences):
            sent_by_key[(pack.slug, sentence.ref)] = (pack, sentence)
            position_by_key[(pack.slug, "sentence", sentence.ref)] = index

    due_states = [s for s in states if s.due_at is not None and s.due_at <= now]
    review_items = _review_items_from_states(
        due_states, pack_order, pack_by_slug, char_by_key, sent_by_key, position_by_key
    )
    new_items = _new_material_items(curriculum, states_by_key)

    items = review_items + new_items
    if not items:
        # Exhaustion: resurface soonest-due introduced units as early reviews.
        items = _review_items_from_states(
            states, pack_order, pack_by_slug, char_by_key, sent_by_key, position_by_key
        )

    batch = items[: max(1, batch_size)]
    if not batch:
        return []
    label = _unit_label(len(states))
    return [replace(batch[0], unit_label=label), *batch[1:]]


# --------------------------------------------------------------------------- #
# Internals.
# --------------------------------------------------------------------------- #
def _state_key(state: ReviewState) -> tuple[str, str, str, str]:
    return (state.pack_slug, state.unit_type, state.unit_ref, state.activity)


def _pack_ref(pack: PackSpec) -> PackRef:
    return PackRef(pack.slug, pack.title, pack.glyph, pack.color)


def _chars_content(chars: Sequence[CharacterSpec]) -> dict[str, Any]:
    return {
        "chars": [
            {"hanzi": c.hanzi, "pinyin": c.pinyin, "meaning": c.meaning} for c in chars
        ]
    }


def _pairs_content(chars: Sequence[CharacterSpec]) -> dict[str, Any]:
    return {
        "pairs": [
            {"hanzi": c.hanzi, "pinyin": c.pinyin, "meaning": c.meaning} for c in chars
        ]
    }


def _sentence_content(sentence: SentenceSpec) -> dict[str, Any]:
    return {
        "hanzi": sentence.hanzi,
        "pinyin": sentence.pinyin,
        "translation": sentence.translation,
    }


def _chunk_sizes(count: int, high: int) -> list[int]:
    """Split ``count`` items into evenly sized chunks, each at most ``high``.

    For ``count > high`` every chunk lands within ``[high // 2 + 1, high]`` for
    the ladder ranges used here (trace ``high=3`` -> 2-3, match ``high=5`` ->
    3-5). A ``count`` at or below ``high`` is a single chunk.
    """
    if count <= 0:
        return []
    if count <= high:
        return [count]
    chunks = ceil(count / high)
    base, remainder = divmod(count, chunks)
    return [base + 1] * remainder + [base] * (chunks - remainder)


def _split[T](seq: Sequence[T], sizes: Sequence[int]) -> list[list[T]]:
    out: list[list[T]] = []
    start = 0
    for size in sizes:
        out.append(list(seq[start : start + size]))
        start += size
    return out


def _new_material_items(
    curriculum: Curriculum,
    states_by_key: dict[tuple[str, str, str, str], ReviewState],
) -> list[ItemSpec]:
    items: list[ItemSpec] = []
    for pack in curriculum.packs:
        ref = _pack_ref(pack)

        trace_chars = [
            c
            for c in pack.characters
            if (pack.slug, "character", c.hanzi, "trace") not in states_by_key
        ]
        for group in _split(trace_chars, _chunk_sizes(len(trace_chars), TRACE_MAX)):
            items.append(
                ItemSpec(
                    activity="trace",
                    kind="new",
                    pack=ref,
                    content=_chars_content(group),
                    units=tuple(
                        ReviewUnit(pack.slug, "character", c.hanzi, "trace")
                        for c in group
                    ),
                )
            )

        match_chars = [
            c
            for c in pack.characters
            if (pack.slug, "character", c.hanzi, "match") not in states_by_key
        ]
        if len(match_chars) >= MATCH_MIN:
            for group in _split(match_chars, _chunk_sizes(len(match_chars), MATCH_MAX)):
                items.append(
                    ItemSpec(
                        activity="match",
                        kind="new",
                        pack=ref,
                        content=_pairs_content(group),
                        units=tuple(
                            ReviewUnit(pack.slug, "character", c.hanzi, "match")
                            for c in group
                        ),
                    )
                )

        for sentence in pack.sentences:
            if (pack.slug, "sentence", sentence.ref, "sentence") in states_by_key:
                continue
            items.append(
                ItemSpec(
                    activity="sentence",
                    kind="new",
                    pack=ref,
                    content=_sentence_content(sentence),
                    units=(
                        ReviewUnit(pack.slug, "sentence", sentence.ref, "sentence"),
                    ),
                )
            )
    return items


def _review_items_from_states(
    states: Sequence[ReviewState],
    pack_order: dict[str, int],
    pack_by_slug: dict[str, PackSpec],
    char_by_key: dict[tuple[str, str], tuple[PackSpec, CharacterSpec]],
    sent_by_key: dict[tuple[str, str], tuple[PackSpec, SentenceSpec]],
    position_by_key: dict[tuple[str, str, str], int],
) -> list[ItemSpec]:
    """Group states by ``(pack, activity)`` into review items, oldest due first.

    States with a ``due_at`` are ordered before undated ones; within each group
    members follow curriculum position, then chunk by activity size. Used both
    for due reviews (caller passes only due states) and for exhaustion
    early-reviews (caller passes every state).
    """
    groups: dict[tuple[str, Activity], list[ReviewState]] = {}
    for state in states:
        groups.setdefault((state.pack_slug, state.activity), []).append(state)

    scheduled: list[tuple[datetime, int, int, ItemSpec]] = []
    undated: list[tuple[int, int, ItemSpec]] = []
    fallback = len(position_by_key)
    for (pack_slug, activity), members in groups.items():
        ordered = _order_states(members, position_by_key, fallback)
        high = MATCH_MAX if activity == "match" else TRACE_MAX
        sizes = (
            [1] * len(ordered)
            if activity == "sentence"
            else _chunk_sizes(len(ordered), high)
        )
        pack_idx = pack_order.get(pack_slug, len(pack_order))
        for chunk in _split(ordered, sizes):
            item = _review_item(chunk, activity, pack_by_slug, char_by_key, sent_by_key)
            if item is None:
                continue
            dued = [s.due_at for s in chunk if s.due_at is not None]
            lead_pos = position_by_key.get(
                (pack_slug, chunk[0].unit_type, chunk[0].unit_ref), fallback
            )
            if dued:
                scheduled.append((min(dued), pack_idx, lead_pos, item))
            else:
                undated.append((pack_idx, lead_pos, item))

    scheduled.sort(key=lambda t: (t[0], t[1], t[2]))
    undated.sort(key=lambda t: (t[0], t[1]))
    return [t[3] for t in scheduled] + [t[2] for t in undated]


def _order_states(
    states: Sequence[ReviewState],
    position_by_key: dict[tuple[str, str, str], int],
    fallback: int,
) -> list[ReviewState]:
    def position(state: ReviewState) -> int:
        return position_by_key.get(
            (state.pack_slug, state.unit_type, state.unit_ref), fallback
        )

    dated = sorted(
        (s for s in states if s.due_at is not None),
        key=lambda s: (s.due_at, position(s)),
    )
    undated = sorted((s for s in states if s.due_at is None), key=position)
    return [*dated, *undated]


def _review_item(
    chunk: Sequence[ReviewState],
    activity: Activity,
    pack_by_slug: dict[str, PackSpec],
    char_by_key: dict[tuple[str, str], tuple[PackSpec, CharacterSpec]],
    sent_by_key: dict[tuple[str, str], tuple[PackSpec, SentenceSpec]],
) -> ItemSpec | None:
    pack_slug = chunk[0].pack_slug
    pack = pack_by_slug.get(pack_slug)
    if pack is None:
        return None
    ref = _pack_ref(pack)

    if activity == "sentence":
        state = chunk[0]
        found = sent_by_key.get((pack_slug, state.unit_ref))
        if found is None:
            return None
        _, sentence = found
        return ItemSpec(
            activity="sentence",
            kind="review",
            pack=ref,
            content=_sentence_content(sentence),
            units=(state.unit,),
        )

    chars: list[CharacterSpec] = []
    units: list[ReviewUnit] = []
    for state in chunk:
        found = char_by_key.get((pack_slug, state.unit_ref))
        if found is None:
            continue
        chars.append(found[1])
        units.append(state.unit)
    if not chars:
        return None
    content = _chars_content(chars) if activity == "trace" else _pairs_content(chars)
    return ItemSpec(
        activity=activity,
        kind="review",
        pack=ref,
        content=content,
        units=tuple(units),
    )


def _unit_label(introduced_count: int) -> str:
    index = introduced_count // UNIT_STRIDE
    number = index + 1
    phrase = UNIT_PHRASES[index % len(UNIT_PHRASES)]
    return f"UNIT {number} · {phrase}"


__all__ = [
    "DEFAULT_BATCH_SIZE",
    "LADDER",
    "UNIT_PHRASES",
    "UNIT_STRIDE",
    "Activity",
    "CharacterSpec",
    "Curriculum",
    "ItemSpec",
    "Kind",
    "PackRef",
    "PackSpec",
    "ReviewState",
    "ReviewUnit",
    "SentenceSpec",
    "UnitType",
    "apply_completion",
    "generate_batch",
]
