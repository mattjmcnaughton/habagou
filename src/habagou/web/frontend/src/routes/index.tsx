import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { getAuthSession, getProgressSummary, listPacks, logout } from "../lib/api";
import type { ProgressSummary } from "../lib/api";

export const Route = createFileRoute("/")({
  component: Index,
});

function Index() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const session = useQuery({ queryKey: ["auth", "session"], queryFn: getAuthSession });
  const packs = useQuery({ queryKey: ["packs"], queryFn: listPacks });
  const progress = useQuery({ queryKey: ["progress"], queryFn: getProgressSummary });
  const displayName = session.data?.user?.display_name ?? session.data?.user?.username ?? "Learner";

  async function handleLogout() {
    await logout();
    queryClient.setQueryData(["auth", "session"], {
      authenticated: false,
      provider: session.data?.provider ?? "keycloak",
      user: null,
    });
    await navigate({ to: "/login" });
  }

  return (
    <main className="min-h-screen bg-ink px-4 py-5 text-porcelain sm:px-6">
      <div className="mx-auto flex min-h-[calc(100vh-2.5rem)] w-full max-w-[440px] flex-col">
        <header className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-baseline gap-2">
              <h1 className="text-[1.45rem] font-bold leading-none tracking-normal">Habagou</h1>
              <span className="font-hanzi text-lg text-jade">哈巴狗</span>
            </div>
            <p className="mt-3 max-w-[17rem] text-base leading-6 text-mist">
              Learn to write Chinese characters, stroke by stroke.
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <div className="flex h-8 max-w-[8rem] items-center gap-2 rounded-full border border-white/10 bg-panel px-3 text-sm text-mist">
              <span className="h-2 w-2 shrink-0 rounded-full bg-jade" />
              <span className="truncate">{displayName}</span>
            </div>
            <button
              className="h-8 rounded-md border border-white/10 bg-panel px-3 text-sm text-mist transition-colors hover:border-clay/40 hover:text-porcelain"
              onClick={() => void handleLogout()}
              type="button"
            >
              Sign out
            </button>
          </div>
        </header>

        {progress.data ? <HomeProgress progress={progress.data} /> : null}

        <section className="mt-4 rounded-lg border border-white/10 bg-panel shadow-panel">
          <div className="flex items-center gap-5 border-b border-white/10 p-5">
            <div className="flex h-24 w-24 shrink-0 items-center justify-center rounded-md bg-jade/10 font-hanzi text-6xl text-jade">
              你
            </div>
            <div>
              <p className="text-sm uppercase tracking-[0.16em] text-mist">Writing bench</p>
              <h2 className="mt-2 text-2xl font-bold leading-tight">Choose a pack</h2>
            </div>
          </div>

          <div className="divide-y divide-white/10">
            {packs.isPending ? <p className="p-5 text-sm text-mist">Loading packs...</p> : null}
            {packs.isError ? (
              <p className="p-5 text-sm text-clay">Packs could not be loaded.</p>
            ) : null}
            {packs.data?.map((pack) => (
              <Link
                aria-label={`${pack.title} pack, ${pack.char_count} characters, ${pack.sentence_count} sentences`}
                className="grid w-full grid-cols-[3.5rem_1fr_auto] items-center gap-4 p-4 text-left transition-colors hover:bg-white/[0.035]"
                key={pack.slug}
                params={{ slug: pack.slug }}
                to="/packs/$slug"
              >
                <span
                  aria-hidden="true"
                  className="flex h-14 w-14 items-center justify-center rounded-md font-hanzi text-3xl"
                  style={{ backgroundColor: `${pack.color}22`, color: pack.color }}
                >
                  {pack.glyph}
                </span>
                <span className="min-w-0">
                  <span className="block text-base font-semibold leading-6">{pack.title}</span>
                  <span className="block text-sm leading-5 text-mist">
                    {pack.char_count} characters · {pack.sentence_count} sentences
                  </span>
                  <span className="mt-2 flex flex-wrap gap-1.5">
                    <ProgressBadge label="trace" completed={pack.progress.trace.completed} />
                    <ProgressBadge label="match" completed={pack.progress.match.completed} />
                    <ProgressBadge label="sentence" completed={pack.progress.sentence.completed} />
                  </span>
                </span>
                <span className="text-2xl text-mist" aria-hidden="true">
                  ›
                </span>
              </Link>
            ))}
          </div>
        </section>

        <footer className="mt-auto pt-8 text-center font-hanzi text-sm text-mist/80">
          一笔一画
        </footer>
      </div>
    </main>
  );
}

function HomeProgress({ progress }: { progress: ProgressSummary }) {
  const completed = progress.daily_goal.completed;
  const target = progress.daily_goal.target;
  const pct = target > 0 ? Math.min(100, Math.round((completed / target) * 100)) : 0;

  return (
    <Link
      aria-label={`Progress today, ${completed} of ${target} complete, ${progress.current_streak}-day streak`}
      className="mt-6 block rounded-lg border border-white/10 bg-panel p-4 transition-colors hover:border-jade/30 hover:bg-white/[0.035]"
      to="/progress"
    >
      <span className="flex items-center justify-between gap-4">
        <span>
          <span className="block text-xs uppercase tracking-[0.16em] text-mist">Today</span>
          <span className="mt-1 block text-base font-bold">
            {completed}/{target} goal
          </span>
        </span>
        <span className="rounded-full border border-jade/30 bg-jade/10 px-3 py-1 text-sm text-jade">
          <span className="font-hanzi">火</span> {progress.current_streak}-day
        </span>
      </span>
      <span className="mt-3 block h-1.5 rounded-full bg-panel2">
        <span className="block h-1.5 rounded-full bg-jade" style={{ width: `${pct}%` }} />
      </span>
      <span className="mt-3 block text-right text-xs font-semibold text-jade">View progress ›</span>
    </Link>
  );
}

function ProgressBadge({ completed, label }: { completed: boolean; label: string }) {
  return (
    <span
      className={
        completed
          ? "rounded-full border border-jade/30 bg-jade/10 px-2 py-0.5 text-xs text-jade"
          : "rounded-full border border-white/10 px-2 py-0.5 text-xs text-mist"
      }
    >
      {completed ? "✓ " : ""}
      {label}
    </span>
  );
}
