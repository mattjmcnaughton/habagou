export type TraceState = {
  characterComplete: boolean;
  characterIndex: number;
  finished: boolean;
  strokeNumber: number;
  strokeTotal: number;
};

export type TraceAction =
  | { type: "characterComplete" }
  | { type: "finish" }
  | { type: "nextCharacter"; characterCount: number }
  | { type: "redoCharacter" }
  | { strokeNumber: number; type: "stroke" }
  | { strokeTotal: number; type: "strokeTotal" };

export function initialTraceState(): TraceState {
  return {
    characterComplete: false,
    characterIndex: 0,
    finished: false,
    strokeNumber: 0,
    strokeTotal: 0,
  };
}

export function traceReducer(state: TraceState, action: TraceAction): TraceState {
  switch (action.type) {
    case "strokeTotal":
      return { ...state, strokeTotal: action.strokeTotal };
    case "stroke":
      return { ...state, strokeNumber: action.strokeNumber };
    case "characterComplete":
      return { ...state, characterComplete: true, strokeNumber: state.strokeTotal };
    case "redoCharacter":
      return { ...state, characterComplete: false, strokeNumber: 0 };
    case "nextCharacter": {
      if (!state.characterComplete || state.characterIndex >= action.characterCount - 1) {
        return state;
      }
      return {
        ...state,
        characterComplete: false,
        characterIndex: state.characterIndex + 1,
        strokeNumber: 0,
        strokeTotal: 0,
      };
    }
    case "finish":
      return state.characterComplete ? { ...state, finished: true } : state;
  }
}

export function traceProgressPercent(state: TraceState, characterCount: number) {
  if (characterCount <= 0) {
    return 0;
  }
  const completedCharacters = state.characterIndex + (state.characterComplete ? 1 : 0);
  return Math.round((completedCharacters / characterCount) * 100);
}

export function currentStrokeLabel(state: TraceState) {
  if (state.characterComplete) {
    return "Character complete";
  }
  if (state.strokeTotal <= 0) {
    return "Trace the character";
  }
  return `Stroke ${Math.min(state.strokeNumber + 1, state.strokeTotal)} of ${state.strokeTotal}`;
}
