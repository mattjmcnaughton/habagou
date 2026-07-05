import type { PackDetail } from "../lib/api";

export const WRONG_PAIR_RESET_MS = 560;

type PackCharacter = PackDetail["characters"][number];

export type MatchSide = "hanzi" | "meaning";

export type MatchCard = {
  key: string;
  label: string;
  pairId: string;
  side: MatchSide;
  sublabel?: string;
};

export type MatchState = {
  completed: boolean;
  completedAtMs: number | null;
  justMatchedPairId: string | null;
  left: MatchCard[];
  matchedPairIds: string[];
  right: MatchCard[];
  selectedKey: string | null;
  startedAtMs: number;
  wrongKeys: string[];
  wrongResetAtMs: number | null;
};

export type MatchAction =
  | { type: "clearJustMatched" }
  | { key: string; nowMs: number; type: "tap" }
  | { nowMs: number; type: "resetWrong" };

export function initialMatchState(
  characters: PackCharacter[],
  options: { nowMs?: number; shuffleSeed?: string | null } = {},
): MatchState {
  const startedAtMs = options.nowMs ?? Date.now();
  const left = characters.map((character, index) => ({
    key: `hanzi-${index}`,
    label: character.hanzi,
    pairId: String(index),
    side: "hanzi" as const,
  }));
  const right = seededShuffle(
    characters.map((character, index) => ({
      key: `meaning-${index}`,
      label: character.meaning,
      pairId: String(index),
      side: "meaning" as const,
      sublabel: character.pinyin,
    })),
    options.shuffleSeed,
  );
  return {
    completed: characters.length === 0,
    completedAtMs: characters.length === 0 ? startedAtMs : null,
    justMatchedPairId: null,
    left,
    matchedPairIds: [],
    right,
    selectedKey: null,
    startedAtMs,
    wrongKeys: [],
    wrongResetAtMs: null,
  };
}

export function matchReducer(state: MatchState, action: MatchAction): MatchState {
  switch (action.type) {
    case "clearJustMatched":
      return { ...state, justMatchedPairId: null };
    case "tap":
      return tapCard(state, action.key, action.nowMs);
    case "resetWrong":
      if (!state.wrongResetAtMs || action.nowMs < state.wrongResetAtMs) {
        return state;
      }
      return { ...state, selectedKey: null, wrongKeys: [], wrongResetAtMs: null };
  }
}

export function matchDurationMs(state: MatchState, nowMs: number): number {
  return Math.max(0, (state.completedAtMs ?? nowMs) - state.startedAtMs);
}

export function matchProgressLabel(state: MatchState): string {
  return `${state.matchedPairIds.length} / ${state.left.length}`;
}

export function formatMatchDuration(durationMs: number): string {
  return `${Math.max(0, Math.round(durationMs / 1000))}s`;
}

function tapCard(state: MatchState, key: string, nowMs: number): MatchState {
  if (state.completed || state.wrongKeys.length > 0) {
    return state;
  }
  const card = findCard(state, key);
  if (!card || state.matchedPairIds.includes(card.pairId)) {
    return state;
  }
  if (!state.selectedKey) {
    return { ...state, selectedKey: card.key };
  }
  if (state.selectedKey === card.key) {
    return { ...state, selectedKey: null };
  }

  const selected = findCard(state, state.selectedKey);
  if (!selected) {
    return { ...state, selectedKey: card.key };
  }
  if (selected.side === card.side) {
    return { ...state, selectedKey: card.key };
  }
  if (selected.pairId !== card.pairId) {
    return {
      ...state,
      wrongKeys: [selected.key, card.key],
      wrongResetAtMs: nowMs + WRONG_PAIR_RESET_MS,
    };
  }

  const matchedPairIds = [...state.matchedPairIds, card.pairId];
  const completed = matchedPairIds.length === state.left.length;
  return {
    ...state,
    completed,
    completedAtMs: completed ? nowMs : null,
    justMatchedPairId: card.pairId,
    matchedPairIds,
    selectedKey: null,
  };
}

function findCard(state: MatchState, key: string): MatchCard | undefined {
  return state.left.concat(state.right).find((card) => card.key === key);
}

function seededShuffle<T>(items: T[], seed: string | null | undefined): T[] {
  const shuffled = [...items];
  const random = seed ? seededRandom(seed) : Math.random;
  for (let index = shuffled.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(random() * (index + 1));
    [shuffled[index], shuffled[swapIndex]] = [shuffled[swapIndex], shuffled[index]];
  }
  return shuffled;
}

function seededRandom(seed: string): () => number {
  let state = 2166136261;
  for (const char of seed) {
    state ^= char.charCodeAt(0);
    state = Math.imul(state, 16777619);
  }
  return () => {
    state += 0x6d2b79f5;
    let value = state;
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}
