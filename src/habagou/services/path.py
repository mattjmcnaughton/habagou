"""Learning Path application service.

Owns the materialized, append-only path queue and the transactional projection
of ``review_states`` over the append-only completion log. The scheduling maths
lives entirely in the pure :mod:`habagou.path_scheduling` module; this service
maps ORM rows onto its plain dataclasses and back.

See ``docs/adrs/0008-review-state-as-rebuildable-projection.md``: every write to
``review_states`` here is reproducible by replaying ``activity_completions``
(``source='path'``) — :meth:`PathService.rebuild_review_states` is that replay.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any, Literal

from habagou import path_scheduling as sched
from habagou.dtos.path import (
    PathContentDTO,
    PathDailyDTO,
    PathDueDTO,
    PathItemCompleteResponseDTO,
    PathItemDTO,
    PathPackDTO,
    PathResponseDTO,
)
from habagou.models import (
    ActivityType,
    CompletionSource,
    PathItem,
    PathItemKind,
    ReviewState,
    ReviewUnitType,
)
from habagou.repositories import (
    PackRepository,
    PathRepository,
    ProgressRepository,
    ReviewStateRepository,
    UserRepository,
)
from habagou.streaks import DAILY_GOAL_TARGET, compute_streaks

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from habagou.models import Pack, User

#: Extend the queue on read while fewer than this many not-done items remain.
PENDING_WINDOW = 10

#: Safety cap on generation passes per read (each pass appends >= 1 item).
_MAX_GENERATION_PASSES = 25

CompleteStatus = Literal["ok", "not_found", "conflict"]


@dataclass(frozen=True)
class RebuiltReviewState:
    """A ``review_states`` row recomputed by replaying the completion log."""

    reps: int
    last_seen_at: datetime | None
    due_at: datetime | None


@dataclass(frozen=True)
class CompleteResult:
    """Outcome of completing a path item, with telemetry metadata."""

    status: CompleteStatus
    response: PathItemCompleteResponseDTO | None = None
    activity: str | None = None
    pack_slug: str | None = None
    kind: str | None = None


class PathService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.pack_repository = PackRepository(session)
        self.path_repository = PathRepository(session)
        self.review_repository = ReviewStateRepository(session)
        self.progress_repository = ProgressRepository(session)
        self.user_repository = UserRepository(session)

    async def get_path(
        self,
        *,
        user: User,
        cursor: int | None = None,
        limit: int = 20,
    ) -> PathResponseDTO:
        packs = await self._published_packs()
        await self._extend_queue(user_id=user.id, packs=packs)

        items = await self.path_repository.list_for_user(user_id=user.id)
        completions = await self.path_repository.completions_by_item(user_id=user.id)
        packs_by_id = {pack.id: pack for pack in packs}
        current = next((it for it in items if it.id not in completions), None)
        today = datetime.now(UTC).date()

        visible = [
            item
            for item in items
            if self._is_visible(item, completions, today)
            and (cursor is None or item.position > cursor)
        ]
        page = visible[:limit]

        due_new = 0
        due_review = 0
        for item in items:
            if item.id in completions:
                continue
            if item.kind is PathItemKind.NEW:
                due_new += 1
            else:
                due_review += 1

        daily, streak = await self._daily_and_streak(user_id=user.id, today=today)
        return PathResponseDTO(
            items=[
                self._item_dto(item, completions, current, packs_by_id) for item in page
            ],
            next_cursor=page[-1].position if page else None,
            daily=daily,
            streak=streak,
            due=PathDueDTO(new=due_new, review=due_review),
        )

    async def complete_item(
        self,
        *,
        user: User,
        item_id: uuid.UUID,
        duration_ms: int,
    ) -> CompleteResult:
        item = await self.path_repository.get_by_id(item_id)
        if item is None or item.user_id != user.id:
            return CompleteResult(status="not_found")

        if await self.path_repository.has_completion(item.id):
            return CompleteResult(status="conflict")

        now = datetime.now(UTC)
        await self.progress_repository.record(
            user_id=user.id,
            pack_id=item.pack_id,
            activity=item.activity,
            duration_ms=duration_ms,
            source=CompletionSource.PATH,
            path_item_id=item.id,
            completed_at=now,
        )
        pack_slug = item.content.get("pack_slug", "")
        for unit in item.content.get("units", []):
            await self._advance_unit(
                user_id=user.id,
                pack_id=item.pack_id,
                pack_slug=pack_slug,
                unit=unit,
                completed_at=now,
            )
        await self.session.commit()

        today = now.date()
        daily, streak = await self._daily_and_streak(user_id=user.id, today=today)
        next_item = await self.path_repository.first_pending(user_id=user.id)
        return CompleteResult(
            status="ok",
            response=PathItemCompleteResponseDTO(
                daily=daily,
                streak=streak,
                item_id=item.id,
                next_item_id=next_item.id if next_item else None,
            ),
            activity=item.activity.value,
            pack_slug=item.content.get("pack_slug"),
            kind=item.kind.value,
        )

    async def rebuild_review_states(
        self, *, user_id: uuid.UUID
    ) -> dict[tuple[uuid.UUID, str, str, str], RebuiltReviewState]:
        """Recompute every review state for a user by replaying the event log.

        Uses only the persisted generation log (``path_items`` and the units
        they introduced, at ``reps=0``) and the ``source='path'`` completions in
        ``completed_at`` order, driven purely by
        :func:`habagou.path_scheduling.apply_completion`. The result should equal
        the live ``review_states`` table field-by-field (ADR-0008).
        """
        items = await self.path_repository.list_for_user(user_id=user_id)
        item_units: dict[uuid.UUID, tuple[uuid.UUID, list[dict[str, Any]]]] = {}
        states: dict[tuple[uuid.UUID, str, str, str], sched.ReviewState] = {}
        for item in items:
            units = item.content.get("units", [])
            pack_slug = item.content.get("pack_slug", "")
            item_units[item.id] = (item.pack_id, units)
            for unit in units:
                key = (
                    item.pack_id,
                    unit["unit_type"],
                    unit["unit_ref"],
                    unit["activity"],
                )
                if key not in states:
                    states[key] = sched.ReviewState(
                        pack_slug=pack_slug,
                        unit_type=unit["unit_type"],
                        unit_ref=unit["unit_ref"],
                        activity=unit["activity"],
                    )

        for (
            path_item_id,
            completed_at,
        ) in await self.path_repository.path_completions_ordered(user_id=user_id):
            pack_id, units = item_units[path_item_id]
            for unit in units:
                key = (pack_id, unit["unit_type"], unit["unit_ref"], unit["activity"])
                states[key] = sched.apply_completion(states[key], completed_at)

        return {
            key: RebuiltReviewState(
                reps=state.reps,
                last_seen_at=state.last_seen_at,
                due_at=state.due_at,
            )
            for key, state in states.items()
        }

    # ------------------------------------------------------------------ #
    # Queue generation.
    # ------------------------------------------------------------------ #
    async def _extend_queue(self, *, user_id: uuid.UUID, packs: list[Pack]) -> None:
        if not packs:
            return
        await self.user_repository.lock_by_id(user_id)
        curriculum = _build_curriculum(packs)
        pack_by_slug = {pack.slug: pack for pack in packs}
        slug_by_pack_id = {pack.id: pack.slug for pack in packs}

        pending = await self.path_repository.count_pending(user_id=user_id)
        passes = 0
        appended = False
        while pending < PENDING_WINDOW and passes < _MAX_GENERATION_PASSES:
            passes += 1
            states = await self.review_repository.list_for_user(user_id=user_id)
            existing_keys = {
                (s.pack_id, s.unit_type.value, s.unit_ref, s.activity.value)
                for s in states
            }
            sched_states = [
                _to_sched_state(state, slug_by_pack_id)
                for state in states
                if state.pack_id in slug_by_pack_id
            ]
            batch = sched.generate_batch(curriculum, sched_states, datetime.now(UTC))
            if not batch:
                break

            base = await self.path_repository.max_position(user_id=user_id) or 0
            for offset, spec in enumerate(batch, start=1):
                pack = pack_by_slug[spec.pack.slug]
                await self.path_repository.append(
                    user_id=user_id,
                    position=base + offset,
                    activity=ActivityType(spec.activity),
                    kind=PathItemKind(spec.kind),
                    pack_id=pack.id,
                    content=_stored_content(spec),
                )
                for unit in spec.units:
                    key = (pack.id, unit.unit_type, unit.unit_ref, unit.activity)
                    if key in existing_keys:
                        continue
                    existing_keys.add(key)
                    await self.review_repository.upsert(
                        user_id=user_id,
                        pack_id=pack.id,
                        unit_type=ReviewUnitType(unit.unit_type),
                        unit_ref=unit.unit_ref,
                        activity=ActivityType(unit.activity),
                        reps=0,
                        last_seen_at=None,
                        due_at=None,
                    )
            appended = True
            pending = await self.path_repository.count_pending(user_id=user_id)

        if appended:
            await self.session.commit()

    # ------------------------------------------------------------------ #
    # Completion helpers.
    # ------------------------------------------------------------------ #
    async def _advance_unit(
        self,
        *,
        user_id: uuid.UUID,
        pack_id: uuid.UUID,
        pack_slug: str,
        unit: dict[str, Any],
        completed_at: datetime,
    ) -> None:
        unit_type = ReviewUnitType(unit["unit_type"])
        activity = ActivityType(unit["activity"])
        existing = await self.review_repository.get(
            user_id=user_id,
            pack_id=pack_id,
            unit_type=unit_type,
            unit_ref=unit["unit_ref"],
            activity=activity,
        )
        current = (
            _to_sched_state(existing, {pack_id: pack_slug})
            if existing is not None
            else sched.ReviewState(
                pack_slug=pack_slug,
                unit_type=unit["unit_type"],
                unit_ref=unit["unit_ref"],
                activity=unit["activity"],
            )
        )
        advanced = sched.apply_completion(current, completed_at)
        if existing is None:
            existing = ReviewState(
                user_id=user_id,
                pack_id=pack_id,
                unit_type=unit_type,
                unit_ref=unit["unit_ref"],
                activity=activity,
                reps=advanced.reps,
                last_seen_at=advanced.last_seen_at,
                due_at=advanced.due_at,
            )
            self.session.add(existing)
        else:
            existing.reps = advanced.reps
            existing.last_seen_at = advanced.last_seen_at
            existing.due_at = advanced.due_at
        await self.session.flush()

    # ------------------------------------------------------------------ #
    # Shared helpers.
    # ------------------------------------------------------------------ #
    async def _published_packs(self) -> list[Pack]:
        return await self.pack_repository.list_published_with_content()

    async def _daily_and_streak(
        self, *, user_id: uuid.UUID, today: date
    ) -> tuple[PathDailyDTO, int]:
        counts = await self.progress_repository.daily_completion_counts(user_id=user_id)
        streaks = compute_streaks(counts, today=today)
        return (
            PathDailyDTO(
                completed=counts.get(today, 0),
                target=DAILY_GOAL_TARGET,
            ),
            streaks.current,
        )

    @staticmethod
    def _is_visible(
        item: PathItem,
        completions: dict[uuid.UUID, datetime],
        today: date,
    ) -> bool:
        completed_at = completions.get(item.id)
        if completed_at is None:
            return True  # current + pending are always shown
        return completed_at.date() == today  # done: only today's

    @staticmethod
    def _item_dto(
        item: PathItem,
        completions: dict[uuid.UUID, datetime],
        current: PathItem | None,
        packs_by_id: dict[uuid.UUID, Pack],
    ) -> PathItemDTO:
        if item.id in completions:
            state: Literal["done", "current", "locked"] = "done"
        elif current is not None and item.id == current.id:
            state = "current"
        else:
            state = "locked"

        # Every path item references a published pack (enforced by the
        # path_item_unpublished_pack invariant), so missing here is a bug.
        pack = packs_by_id[item.pack_id]
        pack_dto = PathPackDTO(
            slug=pack.slug,
            title=pack.title,
            glyph=pack.glyph,
            color=pack.color,
        )
        return PathItemDTO(
            id=item.id,
            position=item.position,
            activity=_ACTIVITY_LITERAL[item.activity],
            kind=_KIND_LITERAL[item.kind],
            state=state,
            unit_label=item.content.get("unit_label"),
            pack=pack_dto,
            content=_content_dto(item),
        )


# ---------------------------------------------------------------------- #
# Pure ORM <-> scheduler mapping.
# ---------------------------------------------------------------------- #
#: StrEnum -> Literal converters so the DTO/scheduler literal fields stay typed
#: without the wire shape changing (the enum ``.value`` is only ``str``).
_ACTIVITY_LITERAL: dict[ActivityType, Literal["trace", "match", "sentence"]] = {
    ActivityType.TRACE: "trace",
    ActivityType.MATCH: "match",
    ActivityType.SENTENCE: "sentence",
}
_KIND_LITERAL: dict[PathItemKind, Literal["new", "review"]] = {
    PathItemKind.NEW: "new",
    PathItemKind.REVIEW: "review",
}
_UNIT_TYPE_LITERAL: dict[ReviewUnitType, Literal["character", "sentence"]] = {
    ReviewUnitType.CHARACTER: "character",
    ReviewUnitType.SENTENCE: "sentence",
}


def _build_curriculum(packs: list[Pack]) -> sched.Curriculum:
    return sched.Curriculum(
        packs=tuple(
            sched.PackSpec(
                slug=pack.slug,
                title=pack.title,
                glyph=pack.glyph,
                color=pack.color,
                characters=tuple(
                    sched.CharacterSpec(
                        hanzi=link.character.hanzi,
                        pinyin=link.pinyin,
                        meaning=link.meaning,
                    )
                    for link in pack.characters
                ),
                sentences=tuple(
                    sched.SentenceSpec(
                        ref=str(sentence.id),
                        hanzi=sentence.hanzi,
                        pinyin=sentence.pinyin,
                        translation=sentence.translation,
                    )
                    for sentence in pack.sentences
                ),
            )
            for pack in packs
        )
    )


def _to_sched_state(
    state: ReviewState, slug_by_pack_id: dict[uuid.UUID, str]
) -> sched.ReviewState:
    return sched.ReviewState(
        pack_slug=slug_by_pack_id[state.pack_id],
        unit_type=_UNIT_TYPE_LITERAL[state.unit_type],
        unit_ref=state.unit_ref,
        activity=_ACTIVITY_LITERAL[state.activity],
        reps=state.reps,
        last_seen_at=state.last_seen_at,
        due_at=state.due_at,
    )


def _stored_content(spec: sched.ItemSpec) -> dict[str, Any]:
    """Pin the generation snapshot in the ``path_items.content`` JSONB column.

    Persists the activity payload, the batch-head ``unit_label`` (a
    generation-time attribute, never display state), the pack slug, and the
    reviewable units the item touches (so completion and projection-replay can
    apply the ladder without re-deriving the curriculum).
    """
    return {
        "unit_label": spec.unit_label,
        "pack_slug": spec.pack.slug,
        "activity_content": spec.content,
        "units": [
            {
                "unit_type": unit.unit_type,
                "unit_ref": unit.unit_ref,
                "activity": unit.activity,
            }
            for unit in spec.units
        ],
    }


def _content_dto(item: PathItem) -> PathContentDTO:
    payload = item.content.get("activity_content", {})
    activity = item.activity.value
    if activity == "trace":
        return PathContentDTO.model_validate({"trace": payload})
    if activity == "match":
        return PathContentDTO.model_validate({"match": payload})
    return PathContentDTO.model_validate({"sentence": payload})
