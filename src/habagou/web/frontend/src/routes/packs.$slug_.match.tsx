import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { CompletionStatus } from "../components/completion-status";
import { MatchRunner } from "../components/match-runner";
import { formatMatchDuration } from "../components/match-state";
import type { PackDetail } from "../lib/api";
import { createCompletion, getPack } from "../lib/api";

export const Route = createFileRoute("/packs/$slug_/match")({
  component: MatchActivity,
});

function MatchActivity() {
  const { slug } = Route.useParams();
  const pack = useQuery({ queryKey: ["pack", slug], queryFn: () => getPack(slug) });

  if (pack.isPending) {
    return <MatchShell slug={slug}>Loading match...</MatchShell>;
  }

  if (pack.isError || !pack.data) {
    return <MatchShell slug={slug}>Match activity could not be loaded.</MatchShell>;
  }

  return <MatchGame key={pack.data.slug} pack={pack.data} />;
}

function MatchGame({ pack }: { pack: PackDetail }) {
  const queryClient = useQueryClient();
  const [durationMs, setDurationMs] = useState<number | null>(null);
  const shuffleSeed = useMemo(
    () => new URLSearchParams(window.location.search).get("shuffleSeed"),
    [],
  );
  const completion = useMutation({
    mutationFn: () =>
      createCompletion({
        activity: "match",
        duration_ms: durationMs ?? 0,
        pack_slug: pack.slug,
      }),
    onSuccess: (result) => {
      queryClient.setQueryData<PackDetail>(["pack", pack.slug], (current) =>
        current ? { ...current, progress: result.progress } : current,
      );
      queryClient.invalidateQueries({ queryKey: ["packs"] });
      queryClient.invalidateQueries({ queryKey: ["pack", pack.slug] });
    },
  });

  useEffect(() => {
    if (durationMs !== null && completion.isIdle) {
      completion.mutate();
    }
  }, [completion, durationMs]);

  if (durationMs !== null) {
    return (
      <main className="min-h-screen bg-ink px-4 py-5 text-porcelain sm:px-6">
        <div className="mx-auto flex min-h-[calc(100vh-2.5rem)] w-full max-w-[440px] flex-col justify-center">
          <section className="rounded-lg border border-white/10 bg-panel p-6 text-center shadow-panel">
            <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-md bg-jade/10 text-4xl text-jade">
              ✓
            </div>
            <h1 className="mt-5 text-2xl font-bold">All matched!</h1>
            <p className="mt-2 text-sm leading-6 text-mist">
              Finished in {formatMatchDuration(durationMs)}.
            </p>
            <CompletionStatus completion={completion} />
            <Link
              className="mt-6 inline-flex w-full justify-center rounded-md bg-jade px-4 py-3 text-sm font-bold text-ink transition-colors hover:bg-jade-bright"
              params={{ slug: pack.slug }}
              to="/packs/$slug"
            >
              Back to {pack.title}
            </Link>
          </section>
        </div>
      </main>
    );
  }

  return (
    <MatchRunner
      backLink={
        <Link
          className="inline-flex py-2 text-sm font-semibold text-mist hover:text-porcelain"
          params={{ slug: pack.slug }}
          to="/packs/$slug"
        >
          ‹ {pack.title}
        </Link>
      }
      onFinish={(finalDuration) => setDurationMs(finalDuration)}
      pairs={pack.characters}
      shuffleSeed={shuffleSeed}
      showTimer
    />
  );
}

function MatchShell({ children, slug }: { children: ReactNode; slug: string }) {
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
