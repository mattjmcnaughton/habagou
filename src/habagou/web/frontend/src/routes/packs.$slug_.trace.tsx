import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useReducer, useRef } from "react";
import { CompletionStatus } from "../components/completion-status";
import { TraceCanvas, type TraceCanvasHandle } from "../components/trace-canvas";
import {
  currentStrokeLabel,
  initialTraceState,
  traceProgressPercent,
  traceReducer,
} from "../components/trace-state";
import type { PackDetail } from "../lib/api";
import { createCompletion, getPack } from "../lib/api";
import { prefetchPackStrokeData } from "../lib/strokes";

export const Route = createFileRoute("/packs/$slug_/trace")({
  component: TraceActivity,
});

function TraceActivity() {
  const { slug } = Route.useParams();
  const queryClient = useQueryClient();
  const canvasRef = useRef<TraceCanvasHandle | null>(null);
  const startedAt = useRef(Date.now());
  const [state, dispatch] = useReducer(traceReducer, undefined, initialTraceState);
  const pack = useQuery({ queryKey: ["pack", slug], queryFn: () => getPack(slug) });
  const completion = useMutation({
    mutationFn: () =>
      createCompletion({
        activity: "trace",
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
    return <TraceShell slug={slug}>Loading trace...</TraceShell>;
  }

  if (pack.isError || !pack.data) {
    return <TraceShell slug={slug}>Trace activity could not be loaded.</TraceShell>;
  }

  if (state.finished) {
    return (
      <main className="min-h-screen bg-ink px-4 py-5 text-porcelain sm:px-6">
        <div className="mx-auto flex min-h-[calc(100vh-2.5rem)] w-full max-w-[440px] flex-col justify-center">
          <section className="rounded-lg border border-white/10 bg-panel p-6 text-center shadow-panel">
            <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-md bg-jade/10 font-hanzi text-4xl text-jade">
              ✓
            </div>
            <h1 className="mt-5 text-2xl font-bold">Pack traced!</h1>
            <p className="mt-2 text-sm leading-6 text-mist">
              You wrote every character in {pack.data.title}.
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

  const character = pack.data.characters[state.characterIndex];
  const isLastCharacter = state.characterIndex >= pack.data.characters.length - 1;

  function nextStep() {
    if (!pack.data) {
      return;
    }
    if (isLastCharacter) {
      dispatch({ type: "finish" });
      return;
    }
    dispatch({ type: "nextCharacter", characterCount: pack.data.characters.length });
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
            {state.characterIndex + 1} / {pack.data.characters.length}
          </span>
        </div>

        <div className="mt-3 h-1 overflow-hidden rounded-full bg-panel">
          <div
            className="h-full rounded-full bg-jade transition-[width]"
            style={{ width: `${traceProgressPercent(state, pack.data.characters.length)}%` }}
          />
        </div>

        <section className="mt-6 text-center">
          <p className="text-xl font-semibold text-jade">{character.pinyin}</p>
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

function TraceShell({ children, slug }: { children: React.ReactNode; slug: string }) {
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
