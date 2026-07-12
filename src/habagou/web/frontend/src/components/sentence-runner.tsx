import { useEffect, useReducer, useRef } from "react";
import type { ReactNode } from "react";
import {
  currentSentenceStrokeLabel,
  initialSentenceState,
  markSentenceComplete,
  sentenceProgressPercent,
  sentenceReducer,
} from "./sentence-state";
import { TraceCanvas, type TraceCanvasHandle } from "./trace-canvas";

// Playable core of the Sentence activity: traces each character of every
// sentence in order. Whole-pack routes pass the pack's full sentence list; the
// lesson runner passes a single-element list built from `item.content.sentence`.
// Data fetching, completion posting, and the done screen live in the caller.

export type SentenceRunnerSentence = {
  hanzi: string;
  pinyin: string;
  translation: string;
};

type SentenceRunnerProps = {
  sentences: SentenceRunnerSentence[];
  backLink: ReactNode;
  onFinish: () => void;
};

export function SentenceRunner({ sentences, backLink, onFinish }: SentenceRunnerProps) {
  const canvasRef = useRef<TraceCanvasHandle | null>(null);
  const onFinishRef = useRef(onFinish);
  const [state, dispatch] = useReducer(sentenceReducer, undefined, initialSentenceState);

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

  const sentence = sentences[state.sentenceIndex];
  const sentenceChars = Array.from(sentence.hanzi);
  const hanzi = sentenceChars[state.characterIndex];
  const isLastSentence = state.sentenceIndex >= sentences.length - 1;
  const currentState = markSentenceComplete(state, sentenceChars.length);
  const isSentenceComplete = currentState.sentenceComplete;

  function completeCharacter() {
    dispatch({
      sentenceComplete: state.characterIndex >= sentenceChars.length - 1,
      type: "characterComplete",
    });
  }

  function nextStep() {
    if (!state.sentenceComplete) {
      dispatch({ characterCount: sentenceChars.length, type: "nextCharacter" });
      return;
    }
    if (isLastSentence) {
      dispatch({ type: "finish" });
      return;
    }
    dispatch({ sentenceCount: sentences.length, type: "nextSentence" });
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
            {state.sentenceIndex + 1} / {sentences.length}
          </span>
        </div>

        <div className="mt-3 h-1 overflow-hidden rounded-full bg-panel">
          <div
            className="h-full rounded-full bg-jade transition-[width]"
            style={{
              width: `${sentenceProgressPercent(state, sentences.length, isSentenceComplete)}%`,
            }}
          />
        </div>

        <section className="mt-6 text-center">
          <h1 className="text-xl font-semibold text-jade">{sentence.translation}</h1>
          <p className="mt-2 text-sm leading-5 text-mist">{sentence.pinyin}</p>
        </section>

        <section className="mt-5 flex justify-center gap-2">
          {sentenceChars.map((character, index) => {
            const done =
              index < state.characterIndex ||
              (index === state.characterIndex && isSentenceComplete);
            const active = index === state.characterIndex && !isSentenceComplete;
            return (
              <span
                className={[
                  "flex h-11 w-11 items-center justify-center rounded-md border font-hanzi text-2xl",
                  done
                    ? "border-jade/30 bg-jade/10 text-jade"
                    : "border-white/10 bg-panel text-mist",
                  active ? "border-jade text-porcelain" : "",
                ].join(" ")}
                key={`${state.sentenceIndex}-${sentence.hanzi}-${index}`}
              >
                {character}
              </span>
            );
          })}
        </section>

        <section className="mt-5 rounded-lg border border-white/10 bg-panel p-3 shadow-panel">
          <TraceCanvas
            hanzi={hanzi}
            key={`${state.sentenceIndex}-${state.characterIndex}-${hanzi}`}
            onComplete={completeCharacter}
            onStroke={(strokeNumber) => dispatch({ strokeNumber, type: "stroke" })}
            onTotal={(strokeTotal) => dispatch({ strokeTotal, type: "strokeTotal" })}
            ref={canvasRef}
            size={384}
          />
        </section>

        <p className="mt-4 min-h-6 text-center text-sm text-mist">
          {currentSentenceStrokeLabel(state)}
        </p>

        {state.characterComplete ? (
          <div className="mt-5">
            <p className="mb-3 text-center text-sm font-semibold text-jade">
              {isSentenceComplete ? (
                <>
                  <span className="font-hanzi text-base">{sentence.hanzi}</span> done.
                </>
              ) : (
                <>
                  Nice. That is <span className="font-hanzi text-base">{hanzi}</span>.
                </>
              )}
            </p>
            <button
              className="w-full rounded-md bg-jade px-4 py-3 text-sm font-bold text-ink transition-colors hover:bg-jade-bright"
              onClick={nextStep}
              type="button"
            >
              {isSentenceComplete
                ? isLastSentence
                  ? "Finish"
                  : "Next sentence"
                : "Next character"}
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
