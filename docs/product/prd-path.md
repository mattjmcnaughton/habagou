# Habagou — PRD Addendum: Learning Path

| | |
|---|---|
| Status | **Final v1.0** — approved for implementation |
| Supersedes | [PRD](prd.md) § 4 non-goal "Spaced-repetition scheduling" |
| Depends on | [PRD](prd.md) v1.0 — packs, activities, users/progress remain as specified there |
| Last updated | 2026-07-12 |

## 1. Summary

The base [PRD](prd.md) shipped Habagou as a pack library: learners pick a pack,
then pick an activity within it. This addendum un-defers spaced repetition and
makes the **Path** — an endless, scheduler-ordered stream of short **path
items** — the default way learners use the app. The learner no longer chooses
what to study next; the Path does, interleaving due reviews with new material
across all packs. Packs remain directly browsable and playable exactly as the
base PRD describes; the Path sits alongside them as a new default surface, not
a replacement.

Terminology in this document (Path, path item, new/review, unit, reviewable
unit) follows `CONTEXT.md` exactly — see that file for full definitions.

## 2. Problem & motivation

The v1 pack library requires the learner to decide what to practice and when
to revisit older material. Nothing resurfaces characters the learner has
already traced once they move to the next pack, so retention is left entirely
to the learner's own discipline. The Path removes that decision: it always
has a single obvious next lesson, and it brings back material the learner is
about to forget before they forget it.

## 3. Goals

1. Make the Path the default screen: on open, the learner sees one clear next
   lesson, not a menu of packs.
2. Resurface previously-practiced material on a predictable, swappable
   spaced-repetition schedule, without requiring the learner to configure
   anything.
3. Keep whole-pack browsing, activities, and progress (as specified in the
   base PRD) fully intact and unaffected by Path activity.
4. Extend — never replace — the existing daily goal, streak, and progress
   surfaces to also account for Path activity.

## 4. Non-goals

- **Per-user goal setting.** The daily goal stays fixed at 3 completions
  (existing `DAILY_GOAL_TARGET`); there is no UI or API to change it per user.
- **Ease factor / adaptive difficulty.** The v1 scheduler is a fixed Leitner
  ladder with a binary (done/not-done) signal — no per-item difficulty rating,
  no SM-2/FSRS-style ease adjustment. The scheduling algorithm is isolated
  behind a stable interface so a more sophisticated algorithm can replace it
  later without changing the Path API or data model.
- **Whole-pack Match best-time changes.** The elapsed-time display on
  completing a whole-pack Match activity (base PRD FR-10) remains a
  whole-pack-Match-only concept; Match path items do not compute or display a
  best time.
- Everything the base PRD already excludes (§ 4) still applies: no
  authentication changes beyond what shipped separately, no native mobile
  apps, no handwriting recognition beyond Hanzi Writer tracing, no audio,
  no traditional characters, no social features.

## 5. Users

Same as the base PRD (§ 5) — the beginner learner is now expected to spend
most of a session in the Path rather than browsing packs directly; the pack
library remains available for learners who want to jump to specific content.

## 6. Functional requirements

### 6.1 The Path (default surface)

- FR-19: On opening the app, the learner lands on the Path — an endless,
  vertically-ordered stream of path items chosen by the scheduler for that
  learner. The learner does not pick what to study next.
- FR-20: The Path never runs out. If there is no due review and no new
  material left to introduce, the scheduler generates further items by
  re-surfacing the soonest-due/weakest reviewable units early.
- FR-21: The Path is drawn across all of the learner's packs, not confined to
  one pack at a time; items are grouped visually under derived, cosmetic
  "unit" labels (e.g. "UNIT 1 · WARMING UP") that carry no scheduling meaning
  and are never persisted.

### 6.2 Path items

- FR-22: A path item is exactly one activity (Trace, Match, or Sentence)
  applied to a small slice of one pack's material: Trace covers 2–3
  characters, Match covers 3–5 pairs, Sentence covers one sentence — never a
  whole pack.
- FR-23: Every path item is classified as **new** or **review**: it is
  *review* if it resurfaces reviewable units the learner has seen before and
  that are currently due; otherwise it is *new* (it introduces at least one
  unseen unit).
- FR-24: Completing the current path item reveals the next item as current;
  completed items remain visible in a done state in the stream.

### 6.3 Spaced repetition (scheduler)

- FR-25: Scheduling operates on **reviewable units**, tracked per learner and
  per activity: for Trace and Match, one unit is one pack character (Trace
  and Match strength are tracked separately for the same character); for
  Sentence, one unit is the whole sentence. Characters that appear in a
  sentence but are not in the pack's character list are traced as part of the
  sentence but are never independently scheduled.
- FR-26: The v1 scheduling algorithm is a fixed Leitner ladder with a binary
  completion signal. Every reviewable unit has `reps` and `due_at`. On
  completing a path item, every reviewable unit in that item advances:
  `reps += 1` and `due_at` is set to completion time plus the ladder interval
  for the new `reps` (ladder: 1, 3, 7, 14, 30 days; reps beyond the ladder's
  length reuse the final interval). There is no partial-credit or
  difficulty-rated signal — only completed or not.
- FR-27: The scheduling algorithm lives in an isolated, swappable module with
  no I/O of its own, so a future algorithm (e.g. SM-2, FSRS) can replace the
  Leitner ladder without changing the Path API, the queue-generation
  contract, or any other surface.
- FR-28: Batch generation prioritizes due reviews (oldest `due_at` first),
  then introduces new material in deterministic curriculum order (packs in
  their configured order, then within a pack: trace items, then a match item
  over recently-introduced characters, then that pack's sentences).

### 6.4 Materialized queue

- FR-29: Path items are materialized ahead of need into an append-only queue:
  once fewer than a fixed pending window of not-yet-done items remain, the
  scheduler generates more at the tail of the queue. Generated items are
  never mutated or deleted after creation.
- FR-30: Each path item's content (the specific characters, pairs, or
  sentence it covers) is pinned — snapshotted — at generation time, so the
  lesson the learner sees does not change even if the underlying pack content
  changes later.
- FR-31: A path item's display state is derived, not stored: **done** if a
  completion event exists for it, **current** if it is the first not-done
  item in the learner's queue, **locked** for everything after that.

### 6.5 Daily goal, streak, and progress

- FR-32: The daily goal (fixed at 3 completions per local day) and the streak
  (consecutive local days the goal was met) count completions from **both**
  whole-pack activities and path items — the same counters the base PRD
  describes (§ 6.5), now fed by two sources instead of one.
- FR-33: Path item completions never affect whole-pack activity completion
  badges. Whole-pack badges (per base PRD FR-3, FR-16) are driven solely by
  completions of the whole-pack activity itself; a learner can fully complete
  a pack's Trace activity via the Path without that pack ever showing a
  completed Trace badge, and vice versa.
- FR-34: The Progress tab gains two additive stats: `characters_traced` —
  the count of distinct pack characters the learner has traced at least once
  (via path Trace items or a completed whole-pack Trace activity) — and
  `packs_completed` — the count of packs where all three whole-pack
  activities are complete (unchanged definition from the base PRD, now
  surfaced as an explicit stat).

## 7. Design requirements

Visual design follows the Learning Path design handoff (goal-ring hero,
spine/node stream, item-scoped full-screen lesson runner) using the same
visual language established in the base PRD § 7 (dark theme, Hanken Grotesk +
Noto Sans SC, touch-first tracing canvas).

## 8. Success metrics

In addition to the base PRD's metrics (§ 8):

- Retention: a completed reviewable unit resurfaces as a review item once due,
  without learner configuration.
- Continuity: the Path always has a current item — the endless-queue property
  (FR-20) never regresses to an empty state.

## 9. Open questions

None outstanding — all decisions were locked during planning (see
`.agentic/learning-path/plan.md`).
