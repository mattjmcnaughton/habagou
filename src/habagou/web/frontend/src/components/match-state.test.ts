import { describe, expect, it } from "vitest";
import {
  WRONG_PAIR_RESET_MS,
  formatMatchDuration,
  initialMatchState,
  matchDurationMs,
  matchProgressLabel,
  matchReducer,
} from "./match-state";

const characters = [
  { hanzi: "你", meaning: "you", pinyin: "nǐ" },
  { hanzi: "好", meaning: "good", pinyin: "hǎo" },
  { hanzi: "我", meaning: "I, me", pinyin: "wǒ" },
];

describe("matchReducer", () => {
  it("[WF-04] selects and deselects a card", () => {
    let state = initialMatchState(characters, { nowMs: 1000, shuffleSeed: "test" });

    state = matchReducer(state, { key: "hanzi-0", nowMs: 1100, type: "tap" });
    expect(state.selectedKey).toBe("hanzi-0");

    state = matchReducer(state, { key: "hanzi-0", nowMs: 1200, type: "tap" });
    expect(state.selectedKey).toBeNull();
  });

  it("[WF-04] replaces the selection when tapping the same side", () => {
    let state = initialMatchState(characters, { nowMs: 1000, shuffleSeed: "test" });

    state = matchReducer(state, { key: "hanzi-0", nowMs: 1100, type: "tap" });
    state = matchReducer(state, { key: "hanzi-1", nowMs: 1200, type: "tap" });

    expect(state.selectedKey).toBe("hanzi-1");
    expect(state.matchedPairIds).toEqual([]);
  });

  it("[WF-04] locks a correct pair", () => {
    let state = initialMatchState(characters, { nowMs: 1000, shuffleSeed: "test" });

    expect(state.justMatchedPairId).toBeNull();

    state = matchReducer(state, { key: "hanzi-0", nowMs: 1100, type: "tap" });
    state = matchReducer(state, { key: "meaning-0", nowMs: 1200, type: "tap" });

    expect(state.selectedKey).toBeNull();
    expect(state.justMatchedPairId).toBe("0");
    expect(state.matchedPairIds).toEqual(["0"]);
    expect(matchProgressLabel(state)).toBe("1 / 3");

    state = matchReducer(state, { type: "clearJustMatched" });
    expect(state.justMatchedPairId).toBeNull();
    expect(state.matchedPairIds).toEqual(["0"]);
  });

  it("[WF-04] marks a wrong pair and resets after 560 ms", () => {
    let state = initialMatchState(characters, { nowMs: 1000, shuffleSeed: "test" });

    state = matchReducer(state, { key: "hanzi-0", nowMs: 1100, type: "tap" });
    state = matchReducer(state, { key: "meaning-1", nowMs: 1200, type: "tap" });

    expect(state.wrongKeys).toEqual(["hanzi-0", "meaning-1"]);
    expect(state.wrongResetAtMs).toBe(1200 + WRONG_PAIR_RESET_MS);

    state = matchReducer(state, { key: "hanzi-2", nowMs: 1300, type: "tap" });
    expect(state.wrongKeys).toEqual(["hanzi-0", "meaning-1"]);

    state = matchReducer(state, { nowMs: 1200 + WRONG_PAIR_RESET_MS - 1, type: "resetWrong" });
    expect(state.wrongKeys).toEqual(["hanzi-0", "meaning-1"]);

    state = matchReducer(state, { nowMs: 1200 + WRONG_PAIR_RESET_MS, type: "resetWrong" });
    expect(state.selectedKey).toBeNull();
    expect(state.wrongKeys).toEqual([]);
  });

  it("[WF-04] completes with elapsed timing after the last pair", () => {
    let state = initialMatchState(characters.slice(0, 2), { nowMs: 1000, shuffleSeed: "test" });

    state = matchReducer(state, { key: "hanzi-0", nowMs: 1500, type: "tap" });
    state = matchReducer(state, { key: "meaning-0", nowMs: 2000, type: "tap" });
    state = matchReducer(state, { key: "hanzi-1", nowMs: 2500, type: "tap" });
    state = matchReducer(state, { key: "meaning-1", nowMs: 3200, type: "tap" });

    expect(state.completed).toBe(true);
    expect(matchDurationMs(state, 9000)).toBe(2200);
    expect(formatMatchDuration(matchDurationMs(state, 9000))).toBe("2s");
  });

  it("[WF-04] shuffles deterministically with a seed", () => {
    const first = initialMatchState(characters, { shuffleSeed: "stable" });
    const second = initialMatchState(characters, { shuffleSeed: "stable" });

    expect(first.right.map((card) => card.key)).toEqual(second.right.map((card) => card.key));
  });
});
