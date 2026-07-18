import { ApiError, type PracticeTurn, type PracticeTurnResponse } from "./api";

// Client-side model of a practice conversation (WF-16, ADR 0011). Conversations
// are EPHEMERAL and CLIENT-HELD: each turn returns opaque history the client
// replays on the next turn, nothing is stored server-side, and discarding this
// state is how a conversation ends. Unlike the generation chat (latest-draft-
// only), every tutor turn is kept in full — the transcript IS the product.
// Failures never discard the conversation: entries and history are kept so the
// learner can retry.

export type PracticeFailureKind =
  | "rate_limited"
  | "provider_failure"
  | "disabled"
  | "invalid_history"
  | "network_error"
  | "unauthenticated";

export type PracticeEntry =
  | { role: "learner"; text: string }
  | { role: "tutor"; kind: "turn"; turn: PracticeTurn }
  | { role: "tutor"; kind: "error"; failure: PracticeFailureKind };

export type PracticePhase = "idle" | "sending";

export type PracticeChatState = {
  entries: PracticeEntry[];
  history: unknown[] | undefined;
  phase: PracticePhase;
};

export function initialPracticeState(): PracticeChatState {
  return {
    entries: [],
    history: undefined,
    phase: "idle",
  };
}

export function beginTurn(state: PracticeChatState, text: string): PracticeChatState {
  // No new turn while one is in flight.
  if (state.phase !== "idle") {
    return state;
  }
  return {
    ...state,
    entries: [...state.entries, { role: "learner", text }],
    phase: "sending",
  };
}

// "Try again" after a retryable failure: re-enter the "sending" phase to
// resubmit the LAST learner message WITHOUT appending a new learner entry — the
// failed turn's bubble is reused, so the transcript keeps exactly one bubble
// per message. No-op (same reference) from a busy phase or before any turn.
export function beginRetry(state: PracticeChatState): PracticeChatState {
  if (state.phase !== "idle" || lastLearnerMessage(state) === undefined) {
    return state;
  }
  return { ...state, phase: "sending" };
}

export function applyTurn(
  state: PracticeChatState,
  response: PracticeTurnResponse,
): PracticeChatState {
  if (state.phase !== "sending") {
    return state;
  }
  return {
    ...state,
    entries: [...state.entries, { role: "tutor", kind: "turn", turn: response.turn }],
    history: response.history,
    phase: "idle",
  };
}

export function applyFailure(
  state: PracticeChatState,
  kind: PracticeFailureKind,
): PracticeChatState {
  // A failure can only land while a turn is in flight; a stray late error in
  // the idle phase is rejected as a no-op (same reference).
  if (state.phase !== "sending") {
    return state;
  }
  return {
    ...state,
    entries: [...state.entries, { role: "tutor", kind: "error", failure: kind }],
    phase: "idle",
  };
}

// The most recent learner message, used to resubmit after a provider/network
// failure ("Try again"). Returns undefined only before the first turn.
export function lastLearnerMessage(state: PracticeChatState): string | undefined {
  for (let index = state.entries.length - 1; index >= 0; index -= 1) {
    const entry = state.entries[index];
    if (entry.role === "learner") {
      return entry.text;
    }
  }
  return undefined;
}

export function describeFailure(error: unknown): PracticeFailureKind {
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
      // A corrupted replayed history or plain request validation (e.g. the
      // message exceeding its length bound).
      return "invalid_history";
    default:
      return "provider_failure";
  }
}
