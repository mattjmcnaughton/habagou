export type SentenceState = {
  characterComplete: boolean;
  characterIndex: number;
  finished: boolean;
  sentenceComplete: boolean;
  sentenceIndex: number;
  strokeNumber: number;
  strokeTotal: number;
};

export type SentenceAction =
  | { strokeTotal: number; type: "strokeTotal" }
  | { strokeNumber: number; type: "stroke" }
  | { sentenceComplete?: boolean; type: "characterComplete" }
  | { type: "redoCharacter" }
  | { characterCount: number; type: "nextCharacter" }
  | { sentenceCount: number; type: "nextSentence" }
  | { type: "finish" };

export function initialSentenceState(): SentenceState {
  return {
    characterComplete: false,
    characterIndex: 0,
    finished: false,
    sentenceComplete: false,
    sentenceIndex: 0,
    strokeNumber: 0,
    strokeTotal: 0,
  };
}

export function sentenceReducer(state: SentenceState, action: SentenceAction): SentenceState {
  switch (action.type) {
    case "strokeTotal":
      return { ...state, strokeTotal: action.strokeTotal };
    case "stroke":
      return { ...state, strokeNumber: action.strokeNumber };
    case "characterComplete":
      return {
        ...state,
        characterComplete: true,
        sentenceComplete: action.sentenceComplete ?? false,
      };
    case "redoCharacter":
      return {
        ...state,
        characterComplete: false,
        sentenceComplete: false,
        strokeNumber: 0,
        strokeTotal: 0,
      };
    case "nextCharacter":
      if (!state.characterComplete || state.characterIndex >= action.characterCount - 1) {
        return state;
      }
      return {
        ...state,
        characterComplete: false,
        characterIndex: state.characterIndex + 1,
        sentenceComplete: false,
        strokeNumber: 0,
        strokeTotal: 0,
      };
    case "nextSentence":
      if (!state.sentenceComplete || state.sentenceIndex >= action.sentenceCount - 1) {
        return state;
      }
      return {
        ...state,
        characterComplete: false,
        characterIndex: 0,
        sentenceComplete: false,
        sentenceIndex: state.sentenceIndex + 1,
        strokeNumber: 0,
        strokeTotal: 0,
      };
    case "finish":
      if (!state.sentenceComplete) {
        return state;
      }
      return { ...state, finished: true };
  }
}

export function markSentenceComplete(state: SentenceState, characterCount: number): SentenceState {
  if (!state.characterComplete || state.characterIndex < characterCount - 1) {
    return state;
  }
  return { ...state, sentenceComplete: true };
}

export function sentenceProgressPercent(
  state: SentenceState,
  sentenceCount: number,
  currentSentenceComplete: boolean,
): number {
  if (sentenceCount === 0) {
    return 100;
  }
  return Math.round(
    ((state.sentenceIndex + (currentSentenceComplete ? 1 : 0)) / sentenceCount) * 100,
  );
}

export function currentSentenceStrokeLabel(state: SentenceState): string {
  if (state.strokeTotal <= 0) {
    return "Trace the character";
  }
  return `Stroke ${Math.min(state.strokeNumber + 1, state.strokeTotal)} of ${state.strokeTotal}`;
}
