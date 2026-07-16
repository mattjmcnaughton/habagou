import { describe, expect, it } from "vitest";
import { ApiError, type GenerationDraftResponse, type PackDraft } from "./api";
import {
  applyDraft,
  applyFailure,
  beginRetry,
  beginSave,
  beginTurn,
  describeFailure,
  initialChatState,
  lastUserTopic,
} from "./generation-chat";

function draftFixture(title: string): PackDraft {
  return {
    title,
    characters: [{ hanzi: "点", pinyin: "diǎn", meaning: "to order" }],
    sentences: [{ hanzi: "我要点菜", pinyin: "wǒ yào diǎn cài", translation: "I want to order" }],
    coverage_note: "Found 1 of 1 characters.",
  };
}

function response(title: string, history: unknown[]): GenerationDraftResponse {
  return { draft: draftFixture(title), history };
}

describe("initialChatState", () => {
  it("[WF-15] starts empty and idle with no history or draft", () => {
    const state = initialChatState();

    expect(state.entries).toEqual([]);
    expect(state.history).toBeUndefined();
    expect(state.draft).toBeNull();
    expect(state.draftVersion).toBe(0);
    expect(state.phase).toBe("idle");
  });
});

describe("beginTurn", () => {
  it("[WF-15] appends a user entry and enters the generating phase", () => {
    const state = beginTurn(initialChatState(), "restaurant");

    expect(state.phase).toBe("generating");
    expect(state.entries).toEqual([{ role: "user", topic: "restaurant" }]);
  });

  it("[WF-15] is a no-op while already generating", () => {
    const generating = beginTurn(initialChatState(), "restaurant");
    const again = beginTurn(generating, "second topic");

    expect(again).toBe(generating);
  });
});

describe("applyDraft", () => {
  it("[WF-15] stores the draft, bumps the version, replaces history, and idles", () => {
    const state = applyDraft(
      beginTurn(initialChatState(), "restaurant"),
      response("At the Restaurant", ["h1"]),
    );

    expect(state.phase).toBe("idle");
    expect(state.draft?.title).toBe("At the Restaurant");
    expect(state.draftVersion).toBe(1);
    expect(state.history).toEqual(["h1"]);
    // The draft entry captures glyph/title/count so a superseded draft can render
    // a compact chip without retaining the whole draft.
    expect(state.entries).toEqual([
      { role: "user", topic: "restaurant" },
      {
        role: "assistant",
        kind: "draft",
        draftVersion: 1,
        glyph: "点",
        title: "At the Restaurant",
        characterCount: 1,
      },
    ]);
  });

  it("[WF-15] accumulates history across two turns, replacing it each time", () => {
    let state = applyDraft(beginTurn(initialChatState(), "restaurant"), response("v1", ["h1"]));
    expect(state.history).toEqual(["h1"]);

    state = beginTurn(state, "add drinks");
    state = applyDraft(state, response("v2", ["h1", "h2"]));

    expect(state.history).toEqual(["h1", "h2"]);
    expect(state.draft?.title).toBe("v2");
    expect(state.draftVersion).toBe(2);
  });

  it("[WF-15] bumps the version on each draft replacement", () => {
    let state = applyDraft(beginTurn(initialChatState(), "a"), response("v1", []));
    state = applyDraft(beginTurn(state, "b"), response("v2", []));

    expect(state.draftVersion).toBe(2);
  });

  it("[WF-15] is a no-op while idle", () => {
    const idle = initialChatState();
    const again = applyDraft(idle, response("v1", ["h1"]));

    expect(again).toBe(idle);
  });
});

describe("applyFailure", () => {
  it("[WF-15] keeps the prior draft, history, and entries after a failure", () => {
    const drafted = applyDraft(
      beginTurn(initialChatState(), "restaurant"),
      response("At the Restaurant", ["h1"]),
    );
    const failing = beginTurn(drafted, "refine");
    const state = applyFailure(failing, "rate_limited", "draft");

    expect(state.phase).toBe("idle");
    expect(state.draft?.title).toBe("At the Restaurant");
    expect(state.draftVersion).toBe(1);
    expect(state.history).toEqual(["h1"]);
    expect(state.entries).toEqual([
      { role: "user", topic: "restaurant" },
      {
        role: "assistant",
        kind: "draft",
        draftVersion: 1,
        glyph: "点",
        title: "At the Restaurant",
        characterCount: 1,
      },
      { role: "user", topic: "refine" },
      { role: "assistant", kind: "error", failure: "rate_limited", source: "draft" },
    ]);
  });

  it("[WF-15] is a no-op while idle", () => {
    const idle = initialChatState();
    const again = applyFailure(idle, "rate_limited", "draft");

    expect(again).toBe(idle);
  });

  it("[WF-15] is a no-op when the failure source doesn't match the phase", () => {
    // A "save" failure landing while still generating (or a "draft" failure while
    // saving) is stale and must be rejected same-reference.
    const generating = beginTurn(initialChatState(), "restaurant");
    expect(applyFailure(generating, "save_rejected", "save")).toBe(generating);

    const drafted = applyDraft(generating, response("At the Restaurant", ["h1"]));
    const saving = beginSave(drafted);
    expect(applyFailure(saving, "provider_failure", "draft")).toBe(saving);
  });

  it("[WF-15] carries a server detail on a save rejection and appends from the saving phase", () => {
    const drafted = applyDraft(
      beginTurn(initialChatState(), "restaurant"),
      response("At the Restaurant", ["h1"]),
    );
    const saving = beginSave(drafted);
    const state = applyFailure(saving, "save_rejected", "save", "missing corpus glyphs: 𡘙");

    expect(state.phase).toBe("idle");
    // The draft survives so the user can keep refining.
    expect(state.draft?.title).toBe("At the Restaurant");
    expect(state.entries[state.entries.length - 1]).toEqual({
      role: "assistant",
      kind: "error",
      failure: "save_rejected",
      source: "save",
      detail: "missing corpus glyphs: 𡘙",
    });
  });
});

describe("beginSave", () => {
  it("[WF-15] enters the saving phase when a draft is present and idle", () => {
    const drafted = applyDraft(
      beginTurn(initialChatState(), "restaurant"),
      response("At the Restaurant", ["h1"]),
    );
    const state = beginSave(drafted);

    expect(state.phase).toBe("saving");
    // No new entry — saving is a phase transition, not a conversation turn.
    expect(state.entries).toEqual(drafted.entries);
  });

  it("[WF-15] is a no-op with no draft or when not idle", () => {
    const empty = initialChatState();
    expect(beginSave(empty)).toBe(empty);

    const generating = beginTurn(empty, "restaurant");
    expect(beginSave(generating)).toBe(generating);
  });
});

describe("beginRetry", () => {
  it("[WF-15] re-enters generating WITHOUT appending a new user entry", () => {
    // A failed first turn: one user bubble + one error entry, back at idle.
    const failed = applyFailure(
      beginTurn(initialChatState(), "restaurant"),
      "provider_failure",
      "draft",
    );
    const entriesBefore = failed.entries;
    const retrying = beginRetry(failed);

    expect(retrying.phase).toBe("generating");
    // No new user bubble — the failed turn's bubble is reused, so the transcript
    // still holds exactly one user entry with the topic.
    expect(retrying.entries).toBe(entriesBefore);
    expect(retrying.entries.filter((entry) => entry.role === "user")).toEqual([
      { role: "user", topic: "restaurant" },
    ]);
    expect(lastUserTopic(retrying)).toBe("restaurant");
  });

  it("[WF-15] is a no-op before any user turn or while busy", () => {
    const empty = initialChatState();
    expect(beginRetry(empty)).toBe(empty);

    const generating = beginTurn(empty, "restaurant");
    expect(beginRetry(generating)).toBe(generating);
  });
});

describe("beginTurn while saving", () => {
  it("[WF-15] blocks a new turn while a save is in flight", () => {
    const drafted = applyDraft(
      beginTurn(initialChatState(), "restaurant"),
      response("At the Restaurant", ["h1"]),
    );
    const saving = beginSave(drafted);
    const again = beginTurn(saving, "refine mid-save");

    expect(again).toBe(saving);
  });
});

describe("lastUserTopic", () => {
  it("[WF-15] returns the most recent user topic across a multi-turn conversation", () => {
    let state = applyDraft(beginTurn(initialChatState(), "restaurant"), response("v1", ["h1"]));
    state = beginTurn(state, "make it harder");
    state = applyFailure(state, "provider_failure", "draft");

    expect(lastUserTopic(state)).toBe("make it harder");
  });

  it("[WF-15] returns undefined before the first turn", () => {
    expect(lastUserTopic(initialChatState())).toBeUndefined();
  });
});

describe("describeFailure", () => {
  function apiError(status: number, code: string): ApiError {
    return new ApiError(`error ${status}`, status, code);
  }

  it("[WF-15] maps status codes to failure kinds by call site", () => {
    expect(describeFailure(apiError(401, "unauthenticated"), "draft")).toBe("unauthenticated");
    expect(describeFailure(apiError(503, "service_unavailable"), "draft")).toBe("disabled");
    expect(describeFailure(apiError(429, "rate_limited"), "draft")).toBe("rate_limited");
    expect(describeFailure(apiError(502, "bad_gateway"), "draft")).toBe("provider_failure");
    expect(describeFailure(apiError(422, "validation_error"), "draft")).toBe("invalid_history");
    expect(describeFailure(apiError(422, "validation_error"), "save")).toBe("save_rejected");
    expect(describeFailure(apiError(500, "internal_error"), "draft")).toBe("provider_failure");
  });

  it("[WF-15] maps a non-ApiError (network failure) to network_error", () => {
    expect(describeFailure(new TypeError("Failed to fetch"), "draft")).toBe("network_error");
    expect(describeFailure(new TypeError("Failed to fetch"), "save")).toBe("network_error");
  });
});
