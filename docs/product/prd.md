# Habagou — Product Requirements Document

| | |
|---|---|
| Status | **Final v1.0** — approved for implementation |
| Author | Generated from validated [prototype](../prototype/Habagou.html) |
| Last updated | 2026-07-03 |
| Changes from v1 | AI pack generation moved to v2 roadmap; anonymous sessions replaced by user-centric model with a shared guest user; Docker Compose confirmed as v1 deploy target |

## 1. Summary

Habagou teaches learners to *write* Chinese characters, not just recognize them. Learners work through themed character packs using three activity types — guided stroke tracing, meaning matching, and sentence tracing. The prototype validated the core interaction loop with four hardcoded packs; v1 productionizes it: pack content and the stroke corpus live in Postgres, served by a FastAPI backend, with per-user progress tracking. v1 ships curated packs only; AI-assisted pack generation is the headline v2 feature.

## 2. Problem & motivation

Most Chinese-learning apps emphasize recognition (flashcards, listening). Handwriting is what cements character structure — stroke order, radicals, composition — but practicing it traditionally requires workbooks and a teacher to check stroke order. Habagou gives immediate, per-stroke feedback in the browser on any touch or mouse device.

## 3. Goals (v1)

1. Ship the three prototype activities (Trace, Match, Sentence) with production quality and parity with the validated prototype UX.
2. Move pack content and the stroke corpus from hardcoded/bundled JS to Postgres, served via API.
3. Track progress (activity completions) per user. v1 has no login; all traffic maps to a shared **guest user**, but the schema and APIs are user-scoped so accounts drop in later without rework.
4. Deployable via Docker Compose (single app image + Postgres), with a clean path to Kubernetes later.

## 4. Non-goals (v1)

- **AI pack generation** — explicitly deferred to v2 (see § 10). The v1 architecture must not preclude it (pack schema supports future `source`/provenance fields).
- Authentication, signup, or multi-user identity. (The guest user is a data-model convention, not a login feature.)
- Native mobile apps (the web app must be responsive and touch-friendly, per the prototype's mobile-first layout).
- Spaced-repetition scheduling.
- Handwriting recognition of free-form writing (stroke-by-stroke tracing via Hanzi Writer only).
- Audio/pronunciation, tones practice, listening exercises.
- Traditional characters (v1 is simplified-only; the stroke corpus supports traditional, so this is a natural extension).
- Social features, leaderboards.

## 5. Users

- **Beginner learner (primary):** knows some pinyin, HSK 1–2 vocabulary, wants structured handwriting practice in short sessions (5–15 min).
- **Admin/curator:** seeds and maintains the pack library (v1: scripts/protected endpoints, no UI).

## 6. Functional requirements

### 6.1 Pack library (Home)

- FR-1: Home screen lists available packs as cards showing title, representative glyph, accent color, and a subtitle of the form "N characters · M sentences" (prototype parity).
- FR-2: Packs are fetched from the API; the four prototype packs (Greetings, Numbers, Family, Food & Drink) ship as seed data with identical content.
- FR-3: Selecting a pack opens the pack screen showing its characters and the three activity entry points, with completion indicators per activity.

### 6.2 Trace activity

- FR-4: For each character in the pack, in order, the learner traces strokes on a Hanzi Writer quiz canvas: outline shown, character hidden, hint auto-shown after 3 misses on a stroke (prototype settings).
- FR-5: UI shows pinyin, meaning, progress within the pack ("2 / 5", percent bar), and a live "Stroke i of N" instruction.
- FR-6: On character completion, the full character is revealed with a short animation and a confirmation ("Nice — that's 你"); learner advances with Next / finishes the pack.
- FR-7: Hint button animates the next stroke; Redo restarts the current character.

### 6.3 Match activity

- FR-8: All pack characters appear as a left column; shuffled meaning+pinyin cards appear as a right column. Learner taps to pair them.
- FR-9: Correct pairs lock and fade; incorrect pairs shake and reset after ~0.5 s (prototype behavior).
- FR-10: On completion, the elapsed time is displayed ("Finished in 34s").

### 6.4 Sentence activity

- FR-11: For each sentence in the pack, the learner traces each character in order; a cell strip shows completed/active/pending characters.
- FR-12: Sentence pinyin and English translation are displayed; per-stroke instruction as in Trace.
- FR-13: Sentences may include characters that are not in the pack's character list (e.g. 很 in 我很好) — every character in a sentence must have stroke data and is traced like any other.

### 6.5 Users & progress

- FR-14: The system models users. Migrations/seeding create one well-known **guest user**; every unauthenticated request acts as that user. No login UI, no signup.
- FR-15: Completing an activity records a completion event (user, pack, activity, duration, timestamp).
- FR-16: The pack screen and home cards reflect the current user's completion state per activity (e.g. checkmarks on completed activities).
- FR-17: All progress APIs are user-scoped in their contract (the user is resolved server-side; v1 always resolves to guest). Adding real authentication later must not change API shapes, only how the user is resolved.

### 6.6 Admin

- FR-18: An admin can unpublish/retire a pack and re-order the library via a script or token-protected endpoint (no UI in v1).

## 7. Design requirements

- Match the prototype's visual language: dark theme (`#0e0f11` background, `#5fb89a` accent), Hanken Grotesk + Noto Sans SC typography, card-based layout, mobile-first sizing.
- Touch-first interaction; tracing must work with finger, stylus, and mouse.
- The tracing canvas sizes to its container (prototype: square, ~300 px min).

## 8. Success metrics

- Activation: ≥ 60 % of new sessions complete at least one Trace character.
- Engagement: median session completes ≥ 1 full activity.
- Performance: stroke-data fetch ≤ 150 ms p95 (cached); time-to-interactive on pack screen ≤ 2 s on mid-range mobile.
- Quality: e2e suite green on desktop and mobile viewports for all three activities.

## 9. Open questions

| # | Question | Default assumption if unanswered |
|---|----------|----------------------------------|
| OQ-1 | Since all progress is shared under one guest user, multiple people using the same deployment will see each other's completions. Acceptable for v1? | Yes — v1 is effectively single-household/single-learner. |
| OQ-2 | Simplified-only for v1? | Yes, simplified-only. |
| OQ-3 | Should "reset my progress" be exposed in the UI, given shared guest progress? | Yes — a simple "reset pack progress" action per pack. |

## 10. v2 roadmap (recorded, not scoped)

- **AI pack generation**: pydantic-ai + OpenAI generates themed packs (characters + pinyin + meanings + sentences), validated against the stroke corpus before publication. The v1 stroke-corpus-in-Postgres decision exists partly to enable this validation.
- **Accounts**: real users replace the guest default; progress model already user-scoped.
- **Kubernetes deployment** following Docker Compose v1.
- Traditional characters; spaced repetition; audio.
