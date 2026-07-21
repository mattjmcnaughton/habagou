import { useEffect, useReducer, useRef } from "react";
import type { ReactNode } from "react";
import { AUDIO_PRONUNCIATION_FLAG, useFeatureFlag } from "@/lib/feature-flags";
import { SpeakButton } from "./speak-button";
import { TraceCanvas, type TraceCanvasHandle } from "./trace-canvas";
import {
  currentStrokeLabel,
  initialTraceState,
  traceProgressPercent,
  traceReducer,
} from "./trace-state";

// Playable core of the Trace activity: renders the top bar, canvas, and the
// character-by-character quiz flow over a list of characters. Data fetching,
// completion posting, and the done screen live in the caller (whole-pack route
// or lesson runner). `onFinish` fires once the last character is completed.

export type TraceRunnerCharacter = {
  hanzi: string;
  pinyin: string;
  meaning: string;
};

type TraceRunnerProps = {
  chars: TraceRunnerCharacter[];
  backLink: ReactNode;
  onFinish: () => void;
};

export function TraceRunner({ chars, backLink, onFinish }: TraceRunnerProps) {
  const canvasRef = useRef<TraceCanvasHandle | null>(null);
  const onFinishRef = useRef(onFinish);
  const audioEnabled = useFeatureFlag(AUDIO_PRONUNCIATION_FLAG);
  const [state, dispatch] = useReducer(traceReducer, undefined, initialTraceState);

  useEffect(() => {
    onFinishRef.current = onFinish;
  }, [onFinish]);

  useEffect(() => {
    if (state.finished) {
      onFinishRef.current();
    }
  }, [state.finished]);

  if (state.finished) {
    return null;
  }

  const character = chars[state.characterIndex];
  const isLastCharacter = state.characterIndex >= chars.length - 1;

  function nextStep() {
    if (isLastCharacter) {
      dispatch({ type: "finish" });
      return;
    }
    dispatch({ type: "nextCharacter", characterCount: chars.length });
  }

  function redoCharacter() {
    dispatch({ type: "redoCharacter" });
    canvasRef.current?.redo();
  }

  return (
    <main className="min-h-screen bg-ink px-4 py-5 text-porcelain sm:px-6">
      <div className="mx-auto w-full max-w-[440px]">
        <div className="flex items-center justify-between gap-4">
          {backLink}
          <span className="text-sm font-semibold text-mist">
            {state.characterIndex + 1} / {chars.length}
          </span>
        </div>

        <div className="mt-3 h-1 overflow-hidden rounded-full bg-panel">
          <div
            className="h-full rounded-full bg-jade transition-[width]"
            style={{ width: `${traceProgressPercent(state, chars.length)}%` }}
          />
        </div>

        <section className="mt-6 text-center">
          <div className="flex items-center justify-center gap-2">
            <p className="text-xl font-semibold text-jade">{character.pinyin}</p>
            {audioEnabled ? (
              <SpeakButton label={`Hear ${character.hanzi}`} size="sm" text={character.hanzi} />
            ) : null}
          </div>
          <h1 className="mt-1 text-sm leading-5 text-mist">{character.meaning}</h1>
        </section>

        <section className="mt-5 rounded-lg border border-white/10 bg-panel p-3 shadow-panel">
          <TraceCanvas
            hanzi={character.hanzi}
            key={character.hanzi}
            onComplete={() => dispatch({ type: "characterComplete" })}
            onStroke={(strokeNumber) => dispatch({ strokeNumber, type: "stroke" })}
            onTotal={(strokeTotal) => dispatch({ strokeTotal, type: "strokeTotal" })}
            ref={canvasRef}
            size={384}
          />
        </section>

        <p className="mt-4 min-h-6 text-center text-sm text-mist">{currentStrokeLabel(state)}</p>

        {state.characterComplete ? (
          <div className="mt-5">
            <p className="mb-3 text-center text-sm font-semibold text-jade">
              Nice. That is <span className="font-hanzi text-base">{character.hanzi}</span>.
            </p>
            <button
              className="w-full rounded-md bg-jade px-4 py-3 text-sm font-bold text-ink transition-colors hover:bg-jade-bright"
              onClick={nextStep}
              type="button"
            >
              {isLastCharacter ? "Finish" : "Next character"}
            </button>
          </div>
        ) : (
          <div className="mt-5 grid grid-cols-2 gap-3">
            <button
              className="rounded-md border border-white/10 bg-panel px-4 py-3 text-sm font-semibold text-porcelain hover:bg-white/[0.035]"
              onClick={() => canvasRef.current?.hint(state.strokeNumber)}
              type="button"
            >
              Hint
            </button>
            <button
              className="rounded-md border border-white/10 bg-panel px-4 py-3 text-sm font-semibold text-porcelain hover:bg-white/[0.035]"
              onClick={redoCharacter}
              type="button"
            >
              Redo
            </button>
          </div>
        )}
      </div>
    </main>
  );
}
