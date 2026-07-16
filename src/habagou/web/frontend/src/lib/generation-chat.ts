import { ApiError, type GenerationDraftResponse, type PackDraft } from "./api";

// Client-side model of the pack-generation conversation (issue #102). The chat
// history is CLIENT-HELD: each draft turn returns opaque history the client
// replays on the next turn, and every turn replaces the working draft. Failures
// never discard the conversation — the prior draft, history, and entries are
// kept so the user can retry (a product requirement).

export type ChatFailureKind =
  | "rate_limited"
  | "provider_failure"
  | "disabled"
  | "save_rejected"
  | "invalid_history"
  | "network_error"
  | "unauthenticated";

export type ChatEntry =
  | { role: "user"; topic: string }
  | {
      role: "assistant";
      kind: "draft";
      draftVersion: number;
      // Captured at draft time so a superseded draft can render as a compact chip
      // (glyph · "Draft N" · title · count) WITHOUT retaining the whole draft: the
      // state keeps only the LATEST draft's full data (latest-only design stands).
      glyph: string;
      title: string;
      characterCount: number;
    }
  | {
      role: "assistant";
      kind: "error";
      failure: ChatFailureKind;
      // Which call site raised the failure. "Try again" (a draft-turn resubmit) is
      // only offered for draft-sourced failures: a save-sourced network/5xx must NOT
      // spawn a new draft turn (the preview's Save button is the retry affordance,
      // and on the navigation-failure path the pack was already saved).
      source: FailureSource;
      // Server-supplied detail for failures that carry one (save_rejected: the
      // missing-glyph list from the grounding backstop). Static-copy kinds omit it.
      detail?: string;
    };

// "saving" is a busy phase distinct from "generating": the composer is disabled
// (a refinement turn mid-save would race the save payload) but no draft turn is
// in flight. Both non-idle phases block a new turn and allow a failure entry.
export type ChatPhase = "idle" | "generating" | "saving";

export type GenerationChatState = {
  entries: ChatEntry[];
  history: unknown[] | undefined;
  draft: PackDraft | null;
  draftVersion: number;
  phase: ChatPhase;
};

// Which call site raised the failure, so a shared 422 can be told apart.
export type FailureSource = "draft" | "save";

export function initialChatState(): GenerationChatState {
  return {
    entries: [],
    history: undefined,
    draft: null,
    draftVersion: 0,
    phase: "idle",
  };
}

export function beginTurn(state: GenerationChatState, topic: string): GenerationChatState {
  // No new turn while a draft turn OR a save is in flight.
  if (state.phase !== "idle") {
    return state;
  }
  return {
    ...state,
    entries: [...state.entries, { role: "user", topic }],
    phase: "generating",
  };
}

// "Try again" after a retryable draft failure (S6-C): re-enter the "generating"
// phase to resubmit the LAST user topic WITHOUT appending a new user entry — the
// failed turn's user bubble is reused, so the transcript keeps exactly ONE bubble
// per topic (a duplicate bubble was the observed bug). No-op (same reference) from
// a busy phase or before any user turn has happened.
export function beginRetry(state: GenerationChatState): GenerationChatState {
  if (state.phase !== "idle" || lastUserTopic(state) === undefined) {
    return state;
  }
  return { ...state, phase: "generating" };
}

export function applyDraft(
  state: GenerationChatState,
  response: GenerationDraftResponse,
): GenerationChatState {
  if (state.phase !== "generating") {
    return state;
  }
  const draftVersion = state.draftVersion + 1;
  const draft = response.draft;
  const glyph = draft.characters[0]?.hanzi ?? draft.title.slice(0, 1);
  return {
    ...state,
    entries: [
      ...state.entries,
      {
        role: "assistant",
        kind: "draft",
        draftVersion,
        glyph,
        title: draft.title,
        characterCount: draft.characters.length,
      },
    ],
    history: response.history,
    draft,
    draftVersion,
    phase: "idle",
  };
}

// Enter the "saving" phase before POSTing the draft, so a save failure can append
// a first-class error entry (applyFailure only appends from a busy phase) and a
// stray refinement turn is blocked while the save is in flight.
export function beginSave(state: GenerationChatState): GenerationChatState {
  if (state.phase !== "idle" || state.draft === null) {
    return state;
  }
  return { ...state, phase: "saving" };
}

export function applyFailure(
  state: GenerationChatState,
  kind: ChatFailureKind,
  source: FailureSource,
  detail?: string,
): GenerationChatState {
  // Bind the failure source to the phase that can produce it: a "draft" failure
  // can only land mid-generation, a "save" failure only mid-save. This rejects a
  // stray failure whose source doesn't match the phase (e.g. a late draft error
  // arriving after a save started) as a no-op (same reference).
  const requiredPhase: ChatPhase = source === "draft" ? "generating" : "saving";
  if (state.phase !== requiredPhase) {
    return state;
  }
  const entry: ChatEntry =
    detail === undefined
      ? { role: "assistant", kind: "error", failure: kind, source }
      : { role: "assistant", kind: "error", failure: kind, source, detail };
  return {
    ...state,
    entries: [...state.entries, entry],
    phase: "idle",
  };
}

// The most recent user topic, used to resubmit after a provider/network failure
// ("Try again"). Returns undefined only before the first turn.
export function lastUserTopic(state: GenerationChatState): string | undefined {
  for (let index = state.entries.length - 1; index >= 0; index -= 1) {
    const entry = state.entries[index];
    if (entry.role === "user") {
      return entry.topic;
    }
  }
  return undefined;
}

export function describeFailure(error: unknown, source: FailureSource): ChatFailureKind {
  if (!(error instanceof ApiError)) {
    // A non-ApiError means fetch itself rejected before any response — most
    // likely the user is offline or the request timed out.
    return "network_error";
  }
  switch (error.status) {
    case 401:
      return "unauthenticated";
    case 503:
      return "disabled";
    case 429:
      return "rate_limited";
    case 502:
      return "provider_failure";
    case 422:
      // On a save turn this is a grounding rejection; on a draft turn it is a
      // corrupted replayed history or plain request validation (e.g. the topic
      // exceeding its length bound). The call site tells them apart.
      return source === "save" ? "save_rejected" : "invalid_history";
    default:
      return "provider_failure";
  }
}
