import { describe, expect, it } from "vitest";
import { ApiError, type PracticeTurnResponse } from "./api";
import {
  type PracticeChatState,
  applyFailure,
  applyTurn,
  beginRetry,
  beginTurn,
  describeFailure,
  initialPracticeState,
  lastLearnerMessage,
} from "./practice-chat";

const turnResponse: PracticeTurnResponse = {
  turn: {
    segments: [
      { hanzi: "你好", pinyin: "nǐ hǎo", english: "Hello!" },
      { hanzi: "你想吃什么", pinyin: "nǐ xiǎng chī shénme", english: "What do you want to eat?" },
    ],
    english_aside: null,
  },
  history: [{ mock: "history" }],
};

function sendingState(text = "ordering food"): PracticeChatState {
  return beginTurn(initialPracticeState(), text);
}

describe("practice-chat state", () => {
  it("beginTurn appends the learner entry and enters the sending phase", () => {
    const state = beginTurn(initialPracticeState(), "ordering food");

    expect(state.entries).toEqual([{ role: "learner", text: "ordering food" }]);
    expect(state.phase).toBe("sending");
    expect(state.history).toBeUndefined();
  });

  it("beginTurn is a no-op while a turn is in flight", () => {
    const state = sendingState();

    expect(beginTurn(state, "another")).toBe(state);
  });

  it("applyTurn appends the tutor turn, stores history, and returns to idle", () => {
    const state = applyTurn(sendingState(), turnResponse);

    expect(state.entries).toHaveLength(2);
    expect(state.entries[1]).toEqual({ role: "tutor", kind: "turn", turn: turnResponse.turn });
    expect(state.history).toEqual(turnResponse.history);
    expect(state.phase).toBe("idle");
  });

  it("applyTurn is a no-op outside the sending phase (a stray late response)", () => {
    const state = initialPracticeState();

    expect(applyTurn(state, turnResponse)).toBe(state);
  });

  it("keeps every tutor turn in the transcript across multiple exchanges", () => {
    // Unlike the generation chat (latest-draft-only), the practice transcript
    // retains each full turn — the conversation IS the product.
    let state = applyTurn(sendingState(), turnResponse);
    state = beginTurn(state, "我要吃饭");
    state = applyTurn(state, turnResponse);

    expect(state.entries).toHaveLength(4);
    expect(state.entries.filter((entry) => entry.role === "tutor")).toHaveLength(2);
  });

  it("applyFailure appends an error entry, keeps history, and returns to idle", () => {
    const withHistory = applyTurn(sendingState(), turnResponse);
    const failed = applyFailure(beginTurn(withHistory, "你好吗"), "provider_failure");

    expect(failed.entries[failed.entries.length - 1]).toEqual({
      role: "tutor",
      kind: "error",
      failure: "provider_failure",
    });
    // The conversation is never discarded on failure.
    expect(failed.history).toEqual(turnResponse.history);
    expect(failed.phase).toBe("idle");
  });

  it("applyFailure is a no-op in the idle phase (a stray late error)", () => {
    const state = initialPracticeState();

    expect(applyFailure(state, "network_error")).toBe(state);
  });

  it("beginRetry re-enters sending without appending a second learner bubble", () => {
    const failed = applyFailure(sendingState("ordering food"), "provider_failure");
    const retrying = beginRetry(failed);

    expect(retrying.phase).toBe("sending");
    expect(retrying.entries.filter((entry) => entry.role === "learner")).toHaveLength(1);
  });

  it("beginRetry is a no-op before any learner turn or while busy", () => {
    const empty = initialPracticeState();
    expect(beginRetry(empty)).toBe(empty);

    const busy = sendingState();
    expect(beginRetry(busy)).toBe(busy);
  });

  it("lastLearnerMessage returns the most recent learner text", () => {
    let state = applyTurn(sendingState("first"), turnResponse);
    state = beginTurn(state, "second");

    expect(lastLearnerMessage(state)).toBe("second");
    expect(lastLearnerMessage(initialPracticeState())).toBeUndefined();
  });
});

describe("describeFailure", () => {
  function apiError(status: number): ApiError {
    return new ApiError("failed", status, `http_${status}`);
  }

  it.each([
    [401, "unauthenticated"],
    [429, "rate_limited"],
    [502, "provider_failure"],
    [503, "disabled"],
    [422, "invalid_history"],
    [500, "provider_failure"],
  ] as const)("maps HTTP %i to %s", (status, kind) => {
    expect(describeFailure(apiError(status))).toBe(kind);
  });

  it("maps a non-ApiError rejection to network_error", () => {
    expect(describeFailure(new TypeError("fetch failed"))).toBe("network_error");
  });
});
