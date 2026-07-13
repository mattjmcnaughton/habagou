import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { CompletionStatus } from "../components/completion-status";
import { TraceRunner } from "../components/trace-runner";
import type { PackDetail } from "../lib/api";
import { createCompletion, getPack } from "../lib/api";
import { prefetchPackStrokeData } from "../lib/strokes";

export const Route = createFileRoute("/packs/$slug_/trace")({
  component: TraceActivity,
});

function TraceActivity() {
  const { slug } = Route.useParams();
  const queryClient = useQueryClient();
  const startedAt = useRef(Date.now());
  const [finished, setFinished] = useState(false);
  const pack = useQuery({ queryKey: ["pack", slug], queryFn: () => getPack(slug) });
  const completion = useMutation({
    mutationFn: () =>
      createCompletion({
        activity: "trace",
        duration_ms: Date.now() - startedAt.current,
        pack_id: pack.data?.id ?? "",
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
    if (finished && completion.isIdle) {
      completion.mutate();
    }
  }, [completion, finished]);

  if (pack.isPending) {
    return <TraceShell slug={slug}>Loading trace...</TraceShell>;
  }

  if (pack.isError || !pack.data) {
    return <TraceShell slug={slug}>Trace activity could not be loaded.</TraceShell>;
  }

  if (finished) {
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

  return (
    <TraceRunner
      backLink={
        <Link
          className="inline-flex py-2 text-sm font-semibold text-mist hover:text-porcelain"
          params={{ slug }}
          to="/packs/$slug"
        >
          ‹ {pack.data.title}
        </Link>
      }
      chars={pack.data.characters}
      onFinish={() => setFinished(true)}
    />
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
