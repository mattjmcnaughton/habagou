import { describe, expect, it } from "vitest";
import {
  currentSentenceStrokeLabel,
  initialSentenceState,
  markSentenceComplete,
  sentenceProgressPercent,
  sentenceReducer,
} from "./sentence-state";

describe("sentenceReducer", () => {
  it("[WF-05] advances through characters in a sentence", () => {
    let state = initialSentenceState();

    state = sentenceReducer(state, { strokeTotal: 2, type: "strokeTotal" });
    state = sentenceReducer(state, { strokeNumber: 1, type: "stroke" });
    expect(currentSentenceStrokeLabel(state)).toBe("Stroke 2 of 2");

    state = sentenceReducer(state, { sentenceComplete: false, type: "characterComplete" });
    state = markSentenceComplete(state, 3);
    expect(state.sentenceComplete).toBe(false);

    state = sentenceReducer(state, { characterCount: 3, type: "nextCharacter" });
    expect(state.characterIndex).toBe(1);
    expect(state.characterComplete).toBe(false);
  });

  it("[WF-05] marks a sentence complete on its last character", () => {
    let state = initialSentenceState();
    state = sentenceReducer(state, { sentenceComplete: false, type: "characterComplete" });
    state = sentenceReducer(state, { characterCount: 3, type: "nextCharacter" });
    state = sentenceReducer(state, { sentenceComplete: false, type: "characterComplete" });
    state = sentenceReducer(state, { characterCount: 3, type: "nextCharacter" });
    state = sentenceReducer(state, { sentenceComplete: true, type: "characterComplete" });
    state = markSentenceComplete(state, 3);

    expect(state.characterIndex).toBe(2);
    expect(state.sentenceComplete).toBe(true);
    expect(sentenceProgressPercent(state, 2, state.sentenceComplete)).toBe(50);
  });

  it("[WF-05] advances to the next sentence only after completion", () => {
    let state = initialSentenceState();

    state = sentenceReducer(state, { sentenceCount: 2, type: "nextSentence" });
    expect(state.sentenceIndex).toBe(0);

    state = sentenceReducer(state, { sentenceComplete: true, type: "characterComplete" });
    state = sentenceReducer(state, { sentenceCount: 2, type: "nextSentence" });

    expect(state.sentenceIndex).toBe(1);
    expect(state.characterIndex).toBe(0);
  });

  it("[WF-05] finishes only after the active sentence is complete", () => {
    let state = initialSentenceState();

    state = sentenceReducer(state, { type: "finish" });
    expect(state.finished).toBe(false);

    state = sentenceReducer(state, { sentenceComplete: true, type: "characterComplete" });
    state = sentenceReducer(state, { type: "finish" });
    expect(state.finished).toBe(true);
  });

  it("[WF-05] resets the active character on redo", () => {
    let state = initialSentenceState();
    state = sentenceReducer(state, { strokeTotal: 3, type: "strokeTotal" });
    state = sentenceReducer(state, { strokeNumber: 2, type: "stroke" });
    state = sentenceReducer(state, { sentenceComplete: false, type: "characterComplete" });

    state = sentenceReducer(state, { type: "redoCharacter" });

    expect(state.characterComplete).toBe(false);
    expect(state.strokeNumber).toBe(0);
    expect(state.strokeTotal).toBe(0);
  });
});
