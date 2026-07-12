# Habagou — Context Glossary

Canonical domain language. Terms here are binding; code and docs should use them
exactly. Glossary only — no implementation details.

## Learning Path

- **Path** — the default way to use Habagou: an ordered, endless stream of path
  items chosen by the scheduler for one learner. The learner does not pick what
  to study next; the Path does.

- **Path item** — one short lesson in the Path. Exactly one activity applied to
  a small slice of one pack's material: Trace (2–3 characters), Match (3–5
  pairs), or Sentence (one sentence). Every path item is either *new* or
  *review*.

- **New / Review** — a path item is a *review* if it resurfaces reviewable
  units the learner has seen before and that are due; otherwise it is *new*
  (introduces at least one unseen unit).

- **Unit (path)** — a cosmetic grouping label over consecutive path items
  (e.g. "UNIT 1 · WARMING UP"). Derived, never persisted; carries no scheduling
  meaning.

- **Reviewable unit** — the thing spaced repetition tracks and schedules, per
  learner and per activity. For Trace and Match: one character as taught in a
  pack (a character has separate Trace and Match strength). For Sentence: the
  whole sentence — its constituent characters are not individually tracked.
  Characters that appear in a sentence but not in the pack's character list
  (e.g. 很 in 我很好) are traced but never scheduled.

## Existing (v1) terms

- **Pack** — a curated set of characters and sentences (Greetings, Numbers,
  Family, Food & Drink in v1). Packs remain directly browsable and playable
  outside the Path.

- **Activity** — one of Trace, Match, Sentence. A *pack activity* runs over the
  whole pack (v1 behavior); a *path item* runs the same activity over a small
  slice.

- **Daily goal** — a fixed target of 3 completions per local day. Both pack
  activities and path items count toward it.

- **Streak** — consecutive local days on which the daily goal was met.
