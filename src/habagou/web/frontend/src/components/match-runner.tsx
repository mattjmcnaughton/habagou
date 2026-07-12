import { useEffect, useReducer, useRef, useState } from "react";
import type { Dispatch, ReactNode } from "react";
import {
  formatMatchDuration,
  initialMatchState,
  matchDurationMs,
  matchProgressLabel,
  matchReducer,
  type MatchCard,
  type MatchState,
} from "./match-state";

// Playable core of the Match activity: the two-column board plus the tap/match
// state machine and timers. Data fetching, completion posting, and the done
// screen live in the caller. `onFinish` reports the final match duration so the
// caller can record it and/or display it.

export type MatchRunnerPair = {
  hanzi: string;
  pinyin: string;
  meaning: string;
};

type MatchRunnerProps = {
  pairs: MatchRunnerPair[];
  backLink: ReactNode;
  onFinish: (durationMs: number) => void;
  shuffleSeed?: string | null;
  showTimer?: boolean;
};

export function MatchRunner({
  pairs,
  backLink,
  onFinish,
  shuffleSeed,
  showTimer = false,
}: MatchRunnerProps) {
  const [state, dispatch] = useReducer(matchReducer, pairs, (characters) =>
    initialMatchState(characters, { shuffleSeed }),
  );
  const [nowMs, setNowMs] = useState(state.startedAtMs);
  const finishedRef = useRef(false);
  const onFinishRef = useRef(onFinish);

  useEffect(() => {
    onFinishRef.current = onFinish;
  }, [onFinish]);

  useEffect(() => {
    if (state.completed) {
      return;
    }
    const timer = window.setInterval(() => setNowMs(Date.now()), 250);
    return () => window.clearInterval(timer);
  }, [state.completed]);

  useEffect(() => {
    if (!state.wrongResetAtMs) {
      return;
    }
    const delay = Math.max(0, state.wrongResetAtMs - Date.now());
    const timer = window.setTimeout(() => {
      dispatch({ nowMs: Date.now(), type: "resetWrong" });
    }, delay);
    return () => window.clearTimeout(timer);
  }, [state.wrongResetAtMs]);

  useEffect(() => {
    if (!state.justMatchedPairId) {
      return;
    }
    const timer = window.setTimeout(() => {
      dispatch({ type: "clearJustMatched" });
    }, 500);
    return () => window.clearTimeout(timer);
  }, [state.justMatchedPairId]);

  useEffect(() => {
    if (state.completed && !finishedRef.current) {
      finishedRef.current = true;
      onFinishRef.current(matchDurationMs(state, Date.now()));
    }
  }, [state]);

  if (state.completed) {
    return null;
  }

  return (
    <main className="min-h-screen bg-ink px-4 py-5 text-porcelain sm:px-6">
      <div className="mx-auto w-full max-w-[520px]">
        <div className="flex items-center justify-between gap-4">
          {backLink}
          <span className="text-sm font-semibold text-mist">
            {matchProgressLabel(state)}
            {showTimer ? ` · ${formatMatchDuration(matchDurationMs(state, nowMs))}` : null}
          </span>
        </div>

        <section className="mt-6">
          <h1 className="text-xl font-bold">Match characters</h1>
          <p className="mt-2 text-sm leading-6 text-mist">Tap a character, then its meaning.</p>
        </section>

        <section className="mt-5 grid grid-cols-2 gap-3" aria-label="Match board">
          <div className="grid gap-3">
            {state.left.map((card) => (
              <MatchCardButton card={card} dispatch={dispatch} key={card.key} state={state} />
            ))}
          </div>
          <div className="grid gap-3">
            {state.right.map((card) => (
              <MatchCardButton card={card} dispatch={dispatch} key={card.key} state={state} />
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}

function MatchCardButton({
  card,
  dispatch,
  state,
}: {
  card: MatchCard;
  dispatch: Dispatch<Parameters<typeof matchReducer>[1]>;
  state: MatchState;
}) {
  const matched = state.matchedPairIds.includes(card.pairId);
  const justMatched = state.justMatchedPairId === card.pairId;
  const selected = state.selectedKey === card.key;
  const wrong = state.wrongKeys.includes(card.key);
  const label =
    card.side === "hanzi" ? `${card.label} character` : `${card.label}, ${card.sublabel}`;
  return (
    <button
      aria-label={label}
      className={[
        "min-h-20 rounded-md border p-3 text-left transition-colors transition-transform duration-200",
        card.side === "hanzi" ? "font-hanzi text-4xl" : "text-base font-semibold",
        !matched && !selected && !wrong ? "border-white/10 bg-panel" : "",
        matched && justMatched
          ? "match-card-correct border-[#7fd0b3] bg-jade/20 shadow-[0_0_0_3px_rgba(95,184,154,0.65)]"
          : "",
        matched && !justMatched ? "border-jade/30 bg-jade/10 opacity-55 duration-300" : "",
        selected && !matched && !wrong
          ? "border-jade bg-jade/10 shadow-[0_0_0_3px_rgba(95,184,154,0.55)] -translate-y-0.5 scale-[1.02]"
          : "",
        wrong ? "match-card-wrong border-clay bg-clay/10" : "",
      ].join(" ")}
      disabled={matched || state.completed}
      onClick={() => dispatch({ key: card.key, nowMs: Date.now(), type: "tap" })}
      type="button"
    >
      <span className="block">{card.label}</span>
      {card.sublabel ? <span className="mt-1 block text-sm text-mist">{card.sublabel}</span> : null}
    </button>
  );
}
