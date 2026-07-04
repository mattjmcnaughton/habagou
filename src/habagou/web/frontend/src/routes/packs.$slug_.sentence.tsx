import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useReducer, useRef } from "react";
import type { ReactNode } from "react";
import { CompletionStatus } from "../components/completion-status";
import {
  currentSentenceStrokeLabel,
  initialSentenceState,
  markSentenceComplete,
  sentenceProgressPercent,
  sentenceReducer,
} from "../components/sentence-state";
import { TraceCanvas, type TraceCanvasHandle } from "../components/trace-canvas";
import type { PackDetail } from "../lib/api";
import { createCompletion, getPack } from "../lib/api";
import { prefetchPackStrokeData } from "../lib/strokes";

export const Route = createFileRoute("/packs/$slug_/sentence")({
  component: SentenceActivity,
});

function SentenceActivity() {
  const { slug } = Route.useParams();
  const queryClient = useQueryClient();
  const canvasRef = useRef<TraceCanvasHandle | null>(null);
  const startedAt = useRef(Date.now());
  const [state, dispatch] = useReducer(sentenceReducer, undefined, initialSentenceState);
  const pack = useQuery({ queryKey: ["pack", slug], queryFn: () => getPack(slug) });
  const completion = useMutation({
    mutationFn: () =>
      createCompletion({
        activity: "sentence",
        duration_ms: Date.now() - startedAt.current,
        pack_slug: slug,
      }),
    onSuccess: (result) => {
      queryClient.setQueryData<PackDetail>(["pack", slug], (current) =>
        current ? { ...current, progress: result.progress } : current,
      );
      queryClient.invalidateQueries({ queryKey: ["packs"] });
      queryClient.invalidateQueries({ queryKey: ["pack", slug] });
    },
  });

  useEffect(() => {
    startedAt.current = Date.now();
  }, []);

  useEffect(() => {
    if (pack.data) {
      void prefetchPackStrokeData(queryClient, pack.data);
    }
  }, [pack.data, queryClient]);

  useEffect(() => {
    if (state.finished && completion.isIdle) {
      completion.mutate();
    }
  }, [completion, state.finished]);

  if (pack.isPending) {
    return <SentenceShell slug={slug}>Loading sentences...</SentenceShell>;
  }

  if (pack.isError || !pack.data) {
    return <SentenceShell slug={slug}>Sentence activity could not be loaded.</SentenceShell>;
  }

  if (state.finished) {
    return (
      <main className="min-h-screen bg-ink px-4 py-5 text-porcelain sm:px-6">
        <div className="mx-auto flex min-h-[calc(100vh-2.5rem)] w-full max-w-[440px] flex-col justify-center">
          <section className="rounded-lg border border-white/10 bg-panel p-6 text-center shadow-panel">
            <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-md bg-jade/10 font-hanzi text-4xl text-jade">
              ✓
            </div>
            <h1 className="mt-5 text-2xl font-bold">Sentences complete!</h1>
            <p className="mt-2 text-sm leading-6 text-mist">
              You wrote every sentence in {pack.data.title}.
            </p>
            <CompletionStatus completion={completion} />
            <Link
              className="mt-6 inline-flex w-full justify-center rounded-md bg-jade px-4 py-3 text-sm font-bold text-ink transition-colors hover:bg-jade-bright"
              params={{ slug }}
              to="/packs/$slug"
            >
              Back to {pack.data.title}
            </Link>
          </section>
        </div>
      </main>
    );
  }

  const sentence = pack.data.sentences[state.sentenceIndex];
  const sentenceChars = Array.from(sentence.hanzi);
  const hanzi = sentenceChars[state.characterIndex];
  const isLastSentence = state.sentenceIndex >= pack.data.sentences.length - 1;
  const currentState = markSentenceComplete(state, sentenceChars.length);
  const isSentenceComplete = currentState.sentenceComplete;

  function completeCharacter() {
    dispatch({
      sentenceComplete: state.characterIndex >= sentenceChars.length - 1,
      type: "characterComplete",
    });
  }

  function nextStep() {
    if (!pack.data) {
      return;
    }
    if (!state.sentenceComplete) {
      dispatch({ characterCount: sentenceChars.length, type: "nextCharacter" });
      return;
    }
    if (isLastSentence) {
      dispatch({ type: "finish" });
      return;
    }
    dispatch({ sentenceCount: pack.data.sentences.length, type: "nextSentence" });
  }

  function redoCharacter() {
    dispatch({ type: "redoCharacter" });
    canvasRef.current?.redo();
  }

  return (
    <main className="min-h-screen bg-ink px-4 py-5 text-porcelain sm:px-6">
      <div className="mx-auto w-full max-w-[440px]">
        <div className="flex items-center justify-between gap-4">
          <Link
            className="inline-flex py-2 text-sm font-semibold text-mist hover:text-porcelain"
            params={{ slug }}
            to="/packs/$slug"
          >
            ‹ {pack.data.title}
          </Link>
          <span className="text-sm font-semibold text-mist">
            {state.sentenceIndex + 1} / {pack.data.sentences.length}
          </span>
        </div>

        <div className="mt-3 h-1 overflow-hidden rounded-full bg-panel">
          <div
            className="h-full rounded-full bg-jade transition-[width]"
            style={{
              width: `${sentenceProgressPercent(state, pack.data.sentences.length, isSentenceComplete)}%`,
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

function SentenceShell({ children, slug }: { children: ReactNode; slug: string }) {
  return (
    <main className="min-h-screen bg-ink px-4 py-5 text-porcelain sm:px-6">
      <div className="mx-auto w-full max-w-[440px]">
        <Link
          className="inline-flex py-2 text-sm font-semibold text-mist"
          params={{ slug }}
          to="/packs/$slug"
        >
          ‹ Pack
        </Link>
        <p className="mt-8 text-sm text-mist">{children}</p>
      </div>
    </main>
  );
}
