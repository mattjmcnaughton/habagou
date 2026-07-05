import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useMemo, useReducer, useRef, useState } from "react";
import type { Dispatch, ReactNode } from "react";
import { CompletionStatus } from "../components/completion-status";
import {
  formatMatchDuration,
  initialMatchState,
  matchDurationMs,
  matchProgressLabel,
  matchReducer,
  type MatchCard,
  type MatchState,
} from "../components/match-state";
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
  const completionDuration = useRef<number | null>(null);
  const shuffleSeed = useMemo(
    () => new URLSearchParams(window.location.search).get("shuffleSeed"),
    [],
  );
  const [state, dispatch] = useReducer(matchReducer, pack.characters, (characters) =>
    initialMatchState(characters, { shuffleSeed }),
  );
  const [nowMs, setNowMs] = useState(state.startedAtMs);
  const completion = useMutation({
    mutationFn: () =>
      createCompletion({
        activity: "match",
        duration_ms: completionDuration.current ?? matchDurationMs(state, Date.now()),
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
    if (state.completed && completion.isIdle) {
      completionDuration.current = matchDurationMs(state, Date.now());
      completion.mutate();
    }
  }, [completion, state]);

  if (state.completed) {
    const duration = formatMatchDuration(matchDurationMs(state, nowMs));
    return (
      <main className="min-h-screen bg-ink px-4 py-5 text-porcelain sm:px-6">
        <div className="mx-auto flex min-h-[calc(100vh-2.5rem)] w-full max-w-[440px] flex-col justify-center">
          <section className="rounded-lg border border-white/10 bg-panel p-6 text-center shadow-panel">
            <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-md bg-jade/10 text-4xl text-jade">
              ✓
            </div>
            <h1 className="mt-5 text-2xl font-bold">All matched!</h1>
            <p className="mt-2 text-sm leading-6 text-mist">Finished in {duration}.</p>
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
    <main className="min-h-screen bg-ink px-4 py-5 text-porcelain sm:px-6">
      <div className="mx-auto w-full max-w-[520px]">
        <div className="flex items-center justify-between gap-4">
          <Link
            className="inline-flex py-2 text-sm font-semibold text-mist hover:text-porcelain"
            params={{ slug: pack.slug }}
            to="/packs/$slug"
          >
            ‹ {pack.title}
          </Link>
          <span className="text-sm font-semibold text-mist">
            {matchProgressLabel(state)} · {formatMatchDuration(matchDurationMs(state, nowMs))}
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
