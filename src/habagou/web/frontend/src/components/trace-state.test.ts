import { describe, expect, it } from "vitest";
import {
  currentStrokeLabel,
  initialTraceState,
  traceProgressPercent,
  traceReducer,
} from "./trace-state";

describe("traceReducer", () => {
  it("[WF-03] tracks stroke counts and character completion", () => {
    let state = initialTraceState();

    state = traceReducer(state, { type: "strokeTotal", strokeTotal: 3 });
    state = traceReducer(state, { type: "stroke", strokeNumber: 1 });

    expect(state.strokeTotal).toBe(3);
    expect(state.strokeNumber).toBe(1);
    expect(currentStrokeLabel(state)).toBe("Stroke 2 of 3");

    state = traceReducer(state, { type: "characterComplete" });

    expect(state.characterComplete).toBe(true);
    expect(state.strokeNumber).toBe(3);
    expect(traceProgressPercent(state, 5)).toBe(20);
  });

  it("[WF-03] advances only after the current character is complete", () => {
    const incomplete = initialTraceState();

    expect(traceReducer(incomplete, { type: "nextCharacter", characterCount: 2 })).toBe(incomplete);

    const complete = traceReducer(incomplete, { type: "characterComplete" });
    const next = traceReducer(complete, { type: "nextCharacter", characterCount: 2 });

    expect(next).toMatchObject({
      characterComplete: false,
      characterIndex: 1,
      strokeNumber: 0,
      strokeTotal: 0,
    });
  });

  it("[WF-03] finishes only after the final character is complete", () => {
    const incomplete = initialTraceState();
    const complete = traceReducer(incomplete, { type: "characterComplete" });

    expect(traceReducer(incomplete, { type: "finish" }).finished).toBe(false);
    expect(traceReducer(complete, { type: "finish" }).finished).toBe(true);
  });
});
