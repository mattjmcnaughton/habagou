import { useMutation, useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import type { PracticeSegment, PracticeTurn } from "../lib/api";
import { ModelSelector } from "../components/model-selector";
import { SpeakButton } from "../components/speak-button";
import { getPracticeStatus, practiceTurn } from "../lib/api";
import type { PracticeChatState, PracticeEntry, PracticeFailureKind } from "../lib/practice-chat";
import {
  applyFailure,
  applyTurn,
  beginRetry,
  beginTurn,
  describeFailure,
  initialPracticeState,
  lastLearnerMessage,
} from "../lib/practice-chat";

// Conversational practice (WF-16, ADR 0011): a text chat with an AI tutor on a
// learner-chosen topic. The tutor replies in per-sentence segments — hanzi with
// pinyin always visible, English one tap away — plus an English "break glass"
// aside when the learner asks for help. Conversations are ephemeral and live in
// the pure `practice-chat` state module; this route only wires those
// transitions to React and renders each phase.
export const Route = createFileRoute("/practice")({
  component: PracticeScreen,
});

// Starter topics offered before the conversation begins. Clicking one submits it.
const STARTER_CHIPS = [
  "Ordering food at a restaurant",
  "Meeting someone new",
  "Asking for directions",
] as const;

// First-class failure copy: each kind renders a headline + body.
export const FAILURE_COPY: Record<PracticeFailureKind, { headline: string; body: string }> = {
  rate_limited: {
    headline: "Take a short break",
    body: "You've sent a lot of messages this hour. Try again in a little while — your conversation is kept.",
  },
  provider_failure: {
    headline: "The tutor didn't respond",
    body: "Something went wrong upstream. Nothing was lost — your last message is still here.",
  },
  disabled: {
    headline: "Practice is off",
    body: "No AI provider is configured on this server, so conversation practice is unavailable until an admin turns it on.",
  },
  invalid_history: {
    headline: "This conversation got out of sync",
    body: "Something about the request didn't line up. Start a new conversation to keep practicing.",
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

// Per-kind visual tone + leading glyph for the error bubble: neutral for a
// non-error "off" state, amber for a soft rate-limit, clay/red for hard failures.
const FAILURE_TONE: Record<PracticeFailureKind, { icon: string; accent: string; border: string }> =
  {
    disabled: { icon: "∅", accent: "text-mist", border: "border-white/15 bg-white/[0.04]" },
    rate_limited: { icon: "◷", accent: "text-brass", border: "border-brass/40 bg-brass/10" },
    provider_failure: { icon: "!", accent: "text-clay", border: "border-clay/40 bg-clay/10" },
    network_error: { icon: "!", accent: "text-clay", border: "border-clay/40 bg-clay/10" },
    invalid_history: { icon: "!", accent: "text-clay", border: "border-clay/40 bg-clay/10" },
    unauthenticated: { icon: "!", accent: "text-clay", border: "border-clay/40 bg-clay/10" },
  };

// Kinds that offer a "Try again" resubmit of the last message. Rate limits
// deliberately omit it (no retry-after data — do not fake a countdown).
const RETRYABLE: ReadonlySet<PracticeFailureKind> = new Set(["provider_failure", "network_error"]);

function PracticeScreen() {
  const [state, setState] = useState<PracticeChatState>(initialPracticeState);
  const [draftText, setDraftText] = useState("");
  // Admin model override (ADM-04): undefined means "server default", so a
  // non-admin (or an untouched picker) never puts a `model` on the wire. The
  // picker is per-request UI, not conversation state — practice-chat.ts is
  // deliberately untouched.
  const [model, setModel] = useState<string | undefined>(undefined);
  const inputRef = useRef<HTMLInputElement>(null);
  const status = useQuery({ queryKey: ["practice-status"], queryFn: getPracticeStatus });

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

  const turnMutation = useMutation({
    mutationFn: (vars: {
      message: string;
      history: unknown[] | undefined;
      model: string | undefined;
    }) => practiceTurn(vars.message, vars.history, vars.model),
    onSuccess: (response) => setState((current) => applyTurn(current, response)),
    onError: (error) => setState((current) => applyFailure(current, describeFailure(error))),
  });

  const sending = state.phase === "sending";
  const started = state.entries.length > 0;

  function submitMessage(raw: string) {
    const trimmed = raw.trim();
    if (trimmed.length === 0 || state.phase !== "idle") {
      return;
    }
    // Guard the in-flight request explicitly rather than relying on the
    // disabled composer to prevent a double submit.
    if (turnMutation.isPending) {
      return;
    }
    setState((current) => beginTurn(current, trimmed));
    setDraftText("");
    turnMutation.mutate({
      message: trimmed,
      history: state.history,
      model: effectiveModel,
    });
  }

  function handleRetry() {
    // Resubmit the last message. Unlike a typed submission this reuses the
    // failed turn's learner bubble via beginRetry — no second bubble — and
    // replays the current history.
    const previous = lastLearnerMessage(state);
    if (previous === undefined || state.phase !== "idle" || turnMutation.isPending) {
      return;
    }
    setState((current) => beginRetry(current));
    turnMutation.mutate({
      message: previous,
      history: state.history,
      model: effectiveModel,
    });
  }

  function handleNewConversation() {
    // Ephemeral by design: discarding the client-held state IS ending the
    // conversation. No server call involved.
    if (state.phase !== "idle") {
      return;
    }
    setState(initialPracticeState());
    setDraftText("");
  }

  // Restore keyboard focus to the composer when a turn finishes: disabling the
  // input mid-flight drops focus to <body>, and nothing else brings it back.
  // Only fire on the sending→idle edge — never grab focus on initial mount.
  const wasSending = useRef(sending);
  useEffect(() => {
    if (wasSending.current && !sending) {
      inputRef.current?.focus();
    }
    wasSending.current = sending;
  }, [sending]);

  // The tab always renders; the screen itself gates on the status probe so a
  // learner is never routed into a flow the /turn endpoint can only 503. The
  // gate applies only BEFORE the conversation starts: a mid-conversation
  // status refetch flipping to disabled must never hide a live transcript
  // (the error copy promises "your conversation is kept") — once started, a
  // flip surfaces as the /turn 503's first-class "disabled" error bubble.
  if (!started && status.data && !status.data.enabled) {
    return (
      <PracticeShell onNewConversation={undefined} started={false}>
        <UnavailableState />
      </PracticeShell>
    );
  }

  // Fail closed while the probe is in flight: no picker (and a disabled
  // composer) until it resolves, so a disabled server never collects a doomed
  // first message. A probe that errs fails open — /turn is the authority and
  // its failure states handle the rest.
  const pickerReady = (status.data?.enabled ?? false) || status.isError;

  return (
    <PracticeShell
      onNewConversation={started && !sending ? handleNewConversation : undefined}
      started={started}
    >
      <div
        className={`flex-1 overflow-y-auto px-4 py-5 ${
          started ? "space-y-4" : "flex flex-col justify-center"
        }`}
      >
        {!started && pickerReady ? <TopicPicker onPick={submitMessage} /> : null}
        {state.entries.map((entry, index) => (
          <ConversationEntry
            busy={sending}
            entry={entry}
            // Only the transcript's LAST entry may offer "Try again": once a
            // retry succeeds or a newer message lands, an older failure's
            // button would resubmit the LATEST learner message — duplicating
            // or misdirecting a turn (entries are append-only, so stale
            // bubbles never leave the transcript).
            isLast={index === state.entries.length - 1}
            // Entries are append-only and never reordered, so the index is a
            // stable key here.
            // biome-ignore lint/suspicious/noArrayIndexKey: append-only log
            key={index}
            onRetry={handleRetry}
          />
        ))}
        {sending ? <ThinkingBubble /> : null}
      </div>

      <Composer
        disabled={sending || (!started && !pickerReady)}
        inputRef={inputRef}
        onChange={setDraftText}
        onSubmit={() => submitMessage(draftText)}
        started={started}
        toolbar={
          showModelPicker ? (
            <ModelSelector
              defaultModel={status.data?.default_model ?? null}
              disabled={sending}
              models={modelOptions}
              onSelect={setModel}
              selected={model}
            />
          ) : null
        }
        value={draftText}
      />
    </PracticeShell>
  );
}

function PracticeShell({
  children,
  onNewConversation,
  started,
}: {
  children: React.ReactNode;
  onNewConversation: (() => void) | undefined;
  started: boolean;
}) {
  return (
    // The root layout pads for the fixed tab bar, so size against the
    // remaining viewport rather than the full screen.
    <main className="flex min-h-[calc(100vh-62px)] flex-col bg-ink text-porcelain">
      <div className="mx-auto flex min-h-[calc(100vh-62px)] w-full max-w-[440px] flex-col">
        <header className="grid grid-cols-[auto_1fr_auto] items-center gap-3 border-b border-white/10 px-4 py-3">
          <span aria-hidden="true" className="w-12" />
          <h1 className="text-center text-base font-bold">
            Practice <span className="font-hanzi text-jade">练习</span>
          </h1>
          {started && onNewConversation ? (
            <button
              className="text-sm font-semibold text-mist transition-colors hover:text-porcelain"
              onClick={onNewConversation}
              type="button"
            >
              New
            </button>
          ) : (
            <span aria-hidden="true" className="w-12" />
          )}
        </header>
        {children}
      </div>
    </main>
  );
}

function ConversationEntry({
  busy,
  entry,
  isLast,
  onRetry,
}: {
  busy: boolean;
  entry: PracticeEntry;
  isLast: boolean;
  onRetry: () => void;
}) {
  if (entry.role === "learner") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl border border-jade/40 bg-jade/10 px-4 py-3 text-porcelain">
          {entry.text}
        </div>
      </div>
    );
  }

  if (entry.kind === "error") {
    return <ErrorBubble busy={busy} failure={entry.failure} isLast={isLast} onRetry={onRetry} />;
  }

  return <TutorBubble turn={entry.turn} />;
}

// A tutor reply: one tappable row per sentence segment (hanzi + pinyin, with
// the English translation revealed per segment on tap) and, when the learner
// asked for help, a visually distinct English aside.
function TutorBubble({ turn }: { turn: PracticeTurn }) {
  return (
    <div className="space-y-2">
      <div className="max-w-[85%] space-y-3 rounded-2xl border border-white/10 bg-panel px-4 py-3">
        {turn.segments.map((segment, index) => (
          // Segments are fixed per turn and never reordered.
          // biome-ignore lint/suspicious/noArrayIndexKey: per-turn render-only list
          <SegmentRow key={index} segment={segment} />
        ))}
      </div>
      {turn.english_aside ? <EnglishAside text={turn.english_aside} /> : null}
    </div>
  );
}

function SegmentRow({ segment }: { segment: PracticeSegment }) {
  const [revealed, setRevealed] = useState(false);
  return (
    <div className="flex items-start gap-2">
      <button
        aria-pressed={revealed}
        className="block flex-1 rounded-lg text-left transition-colors hover:bg-white/[0.04]"
        onClick={() => setRevealed((current) => !current)}
        title={revealed ? "Hide translation" : "Show translation"}
        type="button"
      >
        <span className="block font-hanzi text-2xl leading-snug">{segment.hanzi}</span>
        <span className="mt-0.5 block text-sm text-jade">{segment.pinyin}</span>
        {revealed ? (
          <span className="mt-0.5 block text-sm text-mist">{segment.english}</span>
        ) : null}
      </button>
      <SpeakButton
        className="mt-0.5"
        label={`Hear ${segment.hanzi}`}
        size="sm"
        text={segment.hanzi}
      />
    </div>
  );
}

// The "break glass" channel: an English explanation the learner asked for,
// rendered apart from the Chinese conversation so the two never blur together.
function EnglishAside({ text }: { text: string }) {
  return (
    <div
      aria-label="English aside"
      className="max-w-[85%] rounded-2xl border border-brass/40 bg-brass/10 px-4 py-3"
      role="note"
    >
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-brass">In English</p>
      <p className="mt-1 text-sm leading-6 text-porcelain">{text}</p>
    </div>
  );
}

function ErrorBubble({
  busy,
  failure,
  isLast,
  onRetry,
}: {
  busy: boolean;
  failure: PracticeFailureKind;
  isLast: boolean;
  onRetry: () => void;
}) {
  const copy = FAILURE_COPY[failure];
  const tone = FAILURE_TONE[failure];
  // Retry is offered only while this failure is the transcript's last word:
  // handleRetry resubmits the LATEST learner message, so a superseded
  // bubble's button would duplicate (retry after success) or misdirect
  // (retry attached to an older message) a turn.
  const canRetry = RETRYABLE.has(failure) && isLast;

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
        </div>
      </div>
    </div>
  );
}

function TopicPicker({ onPick }: { onPick: (topic: string) => void }) {
  return (
    <div className="flex flex-col items-center pt-6">
      <span
        aria-hidden="true"
        className="flex h-20 w-20 items-center justify-center rounded-2xl bg-jade/10 font-hanzi text-5xl text-jade"
      >
        聊
      </span>
      <p className="mt-6 text-center text-xl font-semibold leading-7">
        What would you like to talk about?
      </p>
      <p className="mt-3 text-center text-sm leading-6 text-mist">
        I'll keep it simple — hanzi with pinyin, English one tap away. Write back in Chinese,
        English, or both.
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

function UnavailableState() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-4 py-5 text-center">
      <span
        aria-hidden="true"
        className="flex h-20 w-20 items-center justify-center rounded-2xl bg-white/[0.04] font-hanzi text-5xl text-mist"
      >
        聊
      </span>
      <p className="mt-6 text-xl font-semibold leading-7">{FAILURE_COPY.disabled.headline}</p>
      <p className="mt-3 max-w-[320px] text-sm leading-6 text-mist">{FAILURE_COPY.disabled.body}</p>
    </div>
  );
}

function ThinkingBubble() {
  return (
    // role="status" mirrors the error bubble's role="alert" so screen readers
    // announce the in-flight state as a live region.
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
        <p className="text-sm leading-6 text-porcelain">Thinking of a reply…</p>
      </div>
    </div>
  );
}

function Composer({
  disabled,
  inputRef,
  onChange,
  onSubmit,
  started,
  toolbar,
  value,
}: {
  disabled: boolean;
  inputRef: React.RefObject<HTMLInputElement | null>;
  onChange: (value: string) => void;
  onSubmit: () => void;
  started: boolean;
  toolbar?: React.ReactNode;
  value: string;
}) {
  const placeholder = disabled
    ? "Waiting for the tutor…"
    : started
      ? "Reply in Chinese, English, or both…"
      : "or type your own topic…";
  return (
    <form
      className="border-t border-white/10 px-4 py-3"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      {/* The model pill (when present) rides in the composer's own toolbar row,
          where model choice belongs — not as a separate menu floating above it. */}
      <div className="rounded-xl border border-white/10 bg-panel">
        {toolbar ? <div className="flex items-center px-2 pt-2">{toolbar}</div> : null}
        <div className="flex items-center gap-2 px-3 py-2">
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
      </div>
    </form>
  );
}
