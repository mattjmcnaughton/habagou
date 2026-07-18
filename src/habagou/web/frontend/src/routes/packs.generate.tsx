import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import type { PackDraft } from "../lib/api";
import { ModelPicker } from "../components/model-picker";
import { ApiError, generateDraft, getGenerationStatus, saveGeneratedPack } from "../lib/api";
import type { ChatEntry, ChatFailureKind, GenerationChatState } from "../lib/generation-chat";
import {
  applyDraft,
  applyFailure,
  beginRetry,
  beginSave,
  beginTurn,
  describeFailure,
  initialChatState,
  lastUserTopic,
} from "../lib/generation-chat";

// Pack-generation chat (issue #102 / HAB-088, mockups S2-S6): the chat scaffold
// and draft preview, refinement turns, save, and first-class failure states. The
// conversation lives in the pure `generation-chat` state module; this route only
// wires those transitions to React and renders each phase.
export const Route = createFileRoute("/packs/generate")({
  component: GeneratePack,
});

// Starter topics offered in the empty state (S2). Clicking one submits it.
const STARTER_CHIPS = [
  "Ordering at a restaurant",
  "Days, dates & the weekend",
  "HSK-1 verbs I keep forgetting",
] as const;

// First-class failure copy (S6): each kind renders a headline + body. save_rejected's
// body is the trailing guidance only — the server's missing-glyph detail is prepended
// at render time from the error entry's `detail`.
export const FAILURE_COPY: Record<ChatFailureKind, { headline: string; body: string }> = {
  rate_limited: {
    headline: "Slow down a moment",
    body: "You've made a lot of requests. Try again in about a minute — your conversation is kept.",
  },
  provider_failure: {
    headline: "The model didn't respond",
    body: "Something went wrong upstream. Nothing was lost — your last message is still here.",
  },
  disabled: {
    headline: "Pack creation is off",
    body: "No AI provider is configured on this server, so pack creation is unavailable until an admin turns it on.",
  },
  save_rejected: {
    headline: "Couldn't save this draft",
    // Self-contained: it reads correctly even when the server sends no detail line
    // above it (no dangling "them"). The missing-glyph detail, when present, is
    // rendered as its own line above this body.
    body: "Some characters aren't traceable yet — keep chatting to swap them out; the pack stays right here.",
  },
  invalid_history: {
    headline: "This conversation got out of sync",
    body: "Something about the request didn't line up. Send your topic again to start a fresh draft.",
  },
  network_error: {
    headline: "Couldn't reach the server",
    body: "Check your connection and try again — your conversation is kept.",
  },
  unauthenticated: {
    headline: "Your session expired",
    body: "Sign in again to keep going — your conversation is kept.",
  },
};

// Per-kind visual tone + leading glyph for the error bubble (S6): neutral for a
// non-error "off" state, amber for a soft rate-limit, clay/red for hard failures.
const FAILURE_TONE: Record<ChatFailureKind, { icon: string; accent: string; border: string }> = {
  disabled: { icon: "∅", accent: "text-mist", border: "border-white/15 bg-white/[0.04]" },
  rate_limited: { icon: "◷", accent: "text-brass", border: "border-brass/40 bg-brass/10" },
  provider_failure: { icon: "!", accent: "text-clay", border: "border-clay/40 bg-clay/10" },
  network_error: { icon: "!", accent: "text-clay", border: "border-clay/40 bg-clay/10" },
  save_rejected: { icon: "!", accent: "text-clay", border: "border-clay/40 bg-clay/10" },
  invalid_history: { icon: "!", accent: "text-clay", border: "border-clay/40 bg-clay/10" },
  unauthenticated: { icon: "!", accent: "text-clay", border: "border-clay/40 bg-clay/10" },
};

// Kinds that offer a "Try again" resubmit of the last topic (S6-C). Rate limits
// deliberately omit it (no retry-after data — do not fake a countdown); disabled
// and save_rejected are not draft-turn retries.
const RETRYABLE: ReadonlySet<ChatFailureKind> = new Set(["provider_failure", "network_error"]);

function GeneratePack() {
  const [state, setState] = useState<GenerationChatState>(initialChatState);
  const [topic, setTopic] = useState("");
  // Admin model override (ADM-04): undefined means "server default", so a
  // non-admin (or an untouched picker) never puts a `model` on the wire. The
  // picker is per-request UI, not conversation state — generation-chat.ts is
  // deliberately untouched.
  const [model, setModel] = useState<string | undefined>(undefined);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  // Same key as packs.index.tsx's entry-point gate, so the cache is shared.
  const status = useQuery({ queryKey: ["generation-status"], queryFn: getGenerationStatus });

  // The server returns `models` (default first) only to admin callers, so the
  // status response itself gates the picker. A single-entry list offers no
  // choice, so it renders nothing either.
  const modelOptions = status.data?.models ?? null;
  const showModelPicker = modelOptions !== null && modelOptions.length >= 2;
  // Never send an override the picker isn't currently offering: a status
  // refetch can withdraw the whole list (admin flag lost) or delist just the
  // selected id (allowlist change on redeploy), and a stale selection must
  // not reach the wire either way — undefined falls back to the server default.
  const effectiveModel =
    showModelPicker && model !== undefined && modelOptions.some((option) => option.id === model)
      ? model
      : undefined;

  const draftMutation = useMutation({
    mutationFn: (vars: {
      topic: string;
      history: unknown[] | undefined;
      model: string | undefined;
    }) => generateDraft(vars.topic, vars.history, vars.model),
    onSuccess: (response) => setState((current) => applyDraft(current, response)),
    onError: (error) =>
      setState((current) => applyFailure(current, describeFailure(error, "draft"), "draft")),
  });

  const saveMutation = useMutation({
    mutationFn: (draft: PackDraft) => saveGeneratedPack(draft),
    // Land the user where the pack now lives. The save itself succeeded here, but
    // we're still in the "saving" phase until navigation completes — if navigation
    // rejects (route load failed/aborted) the UI would otherwise soft-lock in
    // "saving" forever, so recover to idle with a network_error bubble. Source is
    // "save" because the phase is still "saving" when the promise rejects.
    onSuccess: (pack) =>
      navigate({ to: "/packs/$packId", params: { packId: pack.id } }).catch(() =>
        setState((current) => applyFailure(current, "network_error", "save")),
      ),
    onError: (error) => {
      const kind = describeFailure(error, "save");
      // Only the grounding backstop (save_rejected) carries a server detail worth
      // surfacing verbatim (the missing-glyph list); other kinds use static copy.
      const detail =
        kind === "save_rejected" && error instanceof ApiError ? error.message : undefined;
      setState((current) => applyFailure(current, kind, "save", detail));
    },
  });

  const generating = state.phase === "generating";
  const saving = state.phase === "saving";
  const busy = generating || saving;

  function submitTopic(raw: string) {
    const trimmed = raw.trim();
    // No new turn while a draft turn or a save is in flight.
    if (trimmed.length === 0 || state.phase !== "idle") {
      return;
    }
    // Guard the in-flight request explicitly rather than relying on the disabled
    // composer to prevent a double submit.
    if (draftMutation.isPending) {
      return;
    }
    setState((current) => beginTurn(current, trimmed));
    setTopic("");
    draftMutation.mutate({
      topic: trimmed,
      history: state.history,
      model: effectiveModel,
    });
  }

  function handleSave() {
    // No-op while a draft turn is in flight (a superseded-draft save race) or
    // while a save is already pending.
    if (state.phase !== "idle" || saveMutation.isPending || state.draft === null) {
      return;
    }
    const draft = state.draft;
    setState((current) => beginSave(current));
    saveMutation.mutate(draft);
  }

  function handleRetry() {
    // Resubmit the last topic (S6-C "Try again"). Unlike a typed submission this
    // reuses the failed turn's user bubble via beginRetry — no second bubble — and
    // replays the current history.
    const previous = lastUserTopic(state);
    if (previous === undefined || state.phase !== "idle" || draftMutation.isPending) {
      return;
    }
    setState((current) => beginRetry(current));
    draftMutation.mutate({
      topic: previous,
      history: state.history,
      model: effectiveModel,
    });
  }

  function handleKeepChatting() {
    inputRef.current?.focus();
  }

  // Restore keyboard focus to the composer when a busy phase finishes: disabling
  // the input mid-flight drops focus to <body>, and nothing else brings it back.
  // Only fire on the busy→idle edge — never grab focus on initial mount.
  const wasBusy = useRef(busy);
  useEffect(() => {
    if (wasBusy.current && !busy) {
      inputRef.current?.focus();
    }
    wasBusy.current = busy;
  }, [busy]);

  return (
    <main className="flex min-h-screen flex-col bg-ink text-porcelain">
      <div className="mx-auto flex min-h-screen w-full max-w-[440px] flex-col">
        <header className="grid grid-cols-[auto_1fr_auto] items-center gap-3 border-b border-white/10 px-4 py-3">
          <Link
            aria-label="Back to packs"
            className="text-sm font-semibold text-mist transition-colors hover:text-porcelain"
            to="/packs"
          >
            ‹ Packs
          </Link>
          <h1 className="text-center text-base font-bold">
            Create a pack <span className="font-hanzi text-jade">造包</span>
          </h1>
          <span aria-hidden="true" className="w-12" />
        </header>

        <div className="flex-1 space-y-4 overflow-y-auto px-4 py-5">
          {state.entries.length === 0 ? <EmptyState onPick={submitTopic} /> : null}
          {state.entries.map((entry, index) => (
            <ConversationEntry
              busy={busy}
              draft={state.draft}
              draftVersion={state.draftVersion}
              entry={entry}
              // Entries are append-only and never reordered, so the index is a
              // stable key here.
              // biome-ignore lint/suspicious/noArrayIndexKey: append-only log
              key={index}
              onKeepChatting={handleKeepChatting}
              onRetry={handleRetry}
              onSave={handleSave}
              saving={saving}
            />
          ))}
          {generating ? <ProgressBubble /> : null}
        </div>

        {showModelPicker ? (
          <ModelPicker
            defaultModel={status.data?.default_model ?? null}
            disabled={busy}
            models={modelOptions}
            onSelect={setModel}
            selected={model}
          />
        ) : null}
        <Composer
          disabled={busy}
          hasDraft={state.draftVersion > 0}
          inputRef={inputRef}
          onChange={setTopic}
          onSubmit={() => submitTopic(topic)}
          saving={saving}
          value={topic}
        />
      </div>
    </main>
  );
}

function ConversationEntry({
  busy,
  draft,
  draftVersion,
  entry,
  onKeepChatting,
  onRetry,
  onSave,
  saving,
}: {
  busy: boolean;
  draft: PackDraft | null;
  draftVersion: number;
  entry: ChatEntry;
  onKeepChatting: () => void;
  onRetry: () => void;
  onSave: () => void;
  saving: boolean;
}) {
  if (entry.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl border border-jade/40 bg-jade/10 px-4 py-3 text-porcelain">
          {entry.topic}
        </div>
      </div>
    );
  }

  if (entry.kind === "error") {
    return (
      <ErrorBubble busy={busy} entry={entry} onKeepChatting={onKeepChatting} onRetry={onRetry} />
    );
  }

  // A draft turn. Once superseded (a newer draft has landed) it collapses to a
  // compact chip built from the fields captured at draft time; the current draft
  // keeps a short lead-in bubble plus the full preview.
  const isCurrent = entry.draftVersion === draftVersion && draft !== null;
  if (!isCurrent) {
    return <SupersededDraftChip entry={entry} />;
  }
  return (
    <div className="space-y-3">
      <div className="max-w-[85%] rounded-2xl border border-white/10 bg-panel px-4 py-3 text-porcelain">
        Here's a draft — take a look.
      </div>
      <DraftPreview
        busy={busy}
        draft={draft}
        draftVersion={draftVersion}
        // The current draft's entry captured the glyph at draft time; reuse it
        // rather than recomputing the same fallback.
        glyph={entry.glyph}
        onKeepChatting={onKeepChatting}
        onSave={onSave}
        saving={saving}
      />
    </div>
  );
}

// A collapsed record of a draft the conversation has moved past (S5): glyph tile,
// "Draft N", title, and character count — all from the entry's captured fields.
function SupersededDraftChip({
  entry,
}: {
  entry: Extract<ChatEntry, { kind: "draft" }>;
}) {
  return (
    <div className="inline-flex max-w-full items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.02] px-4 py-3 text-sm text-mist">
      <span aria-hidden="true" className="font-hanzi text-2xl leading-none text-brass/70">
        {entry.glyph}
      </span>
      <span className="min-w-0 truncate">
        Draft {entry.draftVersion} · {entry.title} · {entry.characterCount} characters
      </span>
    </div>
  );
}

// First-class failure bubble (S6): headline + body, tone-coded per kind, with an
// optional "Try again" action (draft-turn retries) or "Keep chatting" action
// (save rejections, S6-D) and a server-supplied detail for save rejections.
function ErrorBubble({
  busy,
  entry,
  onKeepChatting,
  onRetry,
}: {
  busy: boolean;
  entry: Extract<ChatEntry, { kind: "error" }>;
  onKeepChatting: () => void;
  onRetry: () => void;
}) {
  const copy = FAILURE_COPY[entry.failure];
  const tone = FAILURE_TONE[entry.failure];
  // "Try again" only for a draft-sourced retryable failure: a save-sourced
  // network/5xx must not spawn a new draft turn (the preview's Save button is the
  // retry affordance, and on the navigation-failure path the pack was already
  // saved — a fresh draft turn could duplicate it).
  const canRetry = RETRYABLE.has(entry.failure) && entry.source === "draft";
  // save_rejected surfaces the server's missing-glyph detail on its own line above
  // the (self-contained) guidance body, and offers "Keep chatting" to swap them.
  const isSaveRejected = entry.failure === "save_rejected";

  return (
    <div className={`max-w-[85%] rounded-2xl border px-4 py-3 ${tone.border}`} role="alert">
      <div className="flex gap-3">
        <span
          aria-hidden="true"
          className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-current text-xs font-bold ${tone.accent}`}
        >
          {tone.icon}
        </span>
        <div className="min-w-0">
          <p className={`text-sm font-bold ${tone.accent}`}>{copy.headline}</p>
          {isSaveRejected && entry.detail ? (
            <p className="mt-1 text-sm leading-6 text-porcelain">{entry.detail}</p>
          ) : null}
          <p className="mt-1 text-sm leading-6 text-porcelain">{copy.body}</p>
          {canRetry ? (
            <button
              className="mt-3 rounded-md bg-clay px-4 py-2 text-sm font-bold text-ink transition-colors hover:bg-clay/90 disabled:opacity-40"
              disabled={busy}
              onClick={onRetry}
              type="button"
            >
              Try again
            </button>
          ) : null}
          {isSaveRejected ? (
            <button
              className="mt-3 rounded-md border border-white/10 px-4 py-2 text-sm font-semibold text-porcelain transition-colors hover:bg-white/[0.05] disabled:opacity-40"
              disabled={busy}
              onClick={onKeepChatting}
              type="button"
            >
              Keep chatting
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function DraftPreview({
  busy,
  draft,
  draftVersion,
  glyph,
  onKeepChatting,
  onSave,
  saving,
}: {
  busy: boolean;
  draft: PackDraft;
  draftVersion: number;
  glyph: string;
  onKeepChatting: () => void;
  onSave: () => void;
  saving: boolean;
}) {
  const charCount = draft.characters.length;
  const sentences = draft.sentences ?? [];

  return (
    <section className="rounded-2xl border border-white/10 bg-panel shadow-panel">
      <div className="flex items-center gap-4 p-4">
        <span
          aria-hidden="true"
          className="flex h-14 w-14 shrink-0 items-center justify-center rounded-md bg-brass/10 font-hanzi text-3xl text-brass"
        >
          {glyph}
        </span>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-bold leading-tight">{draft.title}</h2>
            {draftVersion >= 2 ? (
              <span className="shrink-0 rounded-full border border-jade/40 px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.12em] text-jade">
                Draft {draftVersion}
              </span>
            ) : null}
          </div>
          <p className="mt-1 text-sm text-mist">
            {charCount} characters · {sentences.length} sentences · draft
          </p>
        </div>
      </div>

      {draft.coverage_note ? (
        <div
          aria-label="Coverage note"
          className="mx-4 flex gap-3 rounded-lg border border-brass/40 bg-brass/10 px-4 py-3"
          role="note"
        >
          <span
            aria-hidden="true"
            className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-brass/60 text-xs font-bold text-brass"
          >
            i
          </span>
          <p className="text-sm leading-6 text-brass">
            <CoverageNoteText note={draft.coverage_note} />
          </p>
        </div>
      ) : null}

      <div className="p-4">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-mist">Characters</p>
        <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3">
          {draft.characters.map((character, index) => (
            <div
              className="flex items-baseline gap-3"
              // Model output isn't guaranteed unique; the list is replaced
              // wholesale per draft, so the index is a stable key here.
              // biome-ignore lint/suspicious/noArrayIndexKey: per-draft render-only list
              key={index}
            >
              <span className="font-hanzi text-4xl leading-none">{character.hanzi}</span>
              <span className="min-w-0">
                <span className="block text-sm text-jade">{character.pinyin}</span>
                <span className="block text-sm text-mist">{character.meaning}</span>
              </span>
            </div>
          ))}
        </div>

        {sentences.length > 0 ? (
          <>
            <p className="mt-5 text-xs font-semibold uppercase tracking-[0.16em] text-mist">
              Sentence drills
            </p>
            <div className="mt-3 space-y-3">
              {sentences.map((sentence, index) => (
                // Model output isn't guaranteed unique; the list is replaced
                // wholesale per draft, so the index is a stable key here.
                // biome-ignore lint/suspicious/noArrayIndexKey: per-draft render-only list
                <div key={index}>
                  <p className="font-hanzi text-lg leading-tight">{sentence.hanzi}</p>
                  <p className="mt-1 text-sm text-mist">
                    {sentence.pinyin} · {sentence.translation}
                  </p>
                </div>
              ))}
            </div>
          </>
        ) : null}
      </div>

      <div className="flex gap-3 border-t border-white/10 p-4">
        <button
          className="flex-1 rounded-md bg-jade px-4 py-3 text-sm font-bold text-ink transition-colors hover:bg-jade-bright disabled:opacity-60"
          disabled={busy}
          onClick={onSave}
          type="button"
        >
          {saving ? "Saving…" : "Save pack"}
        </button>
        <button
          className="flex-1 rounded-md border border-white/10 px-4 py-3 text-sm font-semibold text-porcelain transition-colors hover:bg-white/[0.05] disabled:opacity-60"
          disabled={busy}
          onClick={onKeepChatting}
          type="button"
        >
          Keep chatting
        </button>
      </div>
    </section>
  );
}

// The mockup bolds the leading "Found N of ~M" clause of the coverage note. The
// note is one opaque string, so bold a conservative leading match and render the
// remainder normally; if it doesn't match the shape, render flat.
function CoverageNoteText({ note }: { note: string }) {
  const match = note.match(/^Found [^;,.]*/);
  if (!match) {
    return <>{note}</>;
  }
  return (
    <>
      <span className="font-semibold">{match[0]}</span>
      {note.slice(match[0].length)}
    </>
  );
}

function EmptyState({ onPick }: { onPick: (topic: string) => void }) {
  return (
    <div className="flex flex-col items-center pt-6">
      <span
        aria-hidden="true"
        className="flex h-20 w-20 items-center justify-center rounded-2xl bg-jade/10 font-hanzi text-5xl text-jade"
      >
        造
      </span>
      <p className="mt-6 text-center text-xl font-semibold leading-7">
        Tell me what you'd like to practice — a topic, a scene, or a handful of words.
      </p>
      <p className="mt-3 text-center text-sm leading-6 text-mist">
        I'll only use characters that live in the writing corpus, so every one is traceable.
      </p>

      <div className="mt-8 w-full">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-mist">Try</p>
        <div className="mt-3 space-y-3">
          {STARTER_CHIPS.map((chip) => (
            <button
              className="w-full rounded-xl border border-white/10 bg-panel px-4 py-3 text-left text-base text-porcelain transition-colors hover:border-jade/40 hover:bg-white/[0.04]"
              key={chip}
              onClick={() => onPick(chip)}
              type="button"
            >
              {chip}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function ProgressBubble() {
  return (
    // role="status" (not <output>) mirrors the error bubble's role="alert" so
    // screen readers announce the in-flight state as a live region.
    // biome-ignore lint/a11y/useSemanticElements: live-region status, not a form output
    <div role="status">
      <div className="inline-flex max-w-[85%] items-center gap-3 rounded-2xl border border-white/10 bg-panel px-4 py-3">
        <span aria-hidden="true" className="flex shrink-0 gap-1">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-jade" />
          <span
            className="h-1.5 w-1.5 animate-pulse rounded-full bg-jade"
            style={{ animationDelay: "0.15s" }}
          />
          <span
            className="h-1.5 w-1.5 animate-pulse rounded-full bg-jade"
            style={{ animationDelay: "0.3s" }}
          />
        </span>
        <p className="text-sm leading-6 text-porcelain">
          Drafting your pack — checking each character against the corpus…
        </p>
      </div>
      <p className="mt-2 text-xs text-mist">This can take 30–60 seconds.</p>
    </div>
  );
}

function Composer({
  disabled,
  hasDraft,
  inputRef,
  onChange,
  onSubmit,
  saving,
  value,
}: {
  disabled: boolean;
  hasDraft: boolean;
  inputRef: React.RefObject<HTMLInputElement | null>;
  onChange: (value: string) => void;
  onSubmit: () => void;
  saving: boolean;
  value: string;
}) {
  // After the first draft the composer becomes the refinement affordance (S5).
  const placeholder = saving
    ? "Saving…"
    : disabled
      ? "Waiting for the draft…"
      : hasDraft
        ? "refine…"
        : "e.g. words for a trip to the market";
  return (
    <form
      className="border-t border-white/10 px-4 py-3"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-panel px-3 py-2">
        <input
          className="flex-1 bg-transparent text-porcelain placeholder:text-mist focus:outline-none disabled:opacity-60"
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          ref={inputRef}
          value={value}
        />
        <button
          aria-label="Send"
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-jade text-ink transition-colors hover:bg-jade-bright disabled:opacity-40"
          disabled={disabled || value.trim().length === 0}
          type="submit"
        >
          <span aria-hidden="true">↑</span>
        </button>
      </div>
    </form>
  );
}
