import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { AppHeader } from "../components/app-header";
import { useLogout } from "../components/use-logout";
import { getProgressSummary, listPacks } from "../lib/api";
import type { PackSummary, ProgressSummary } from "../lib/api";
import {
  currentMonth,
  heatmapLevelClass,
  last14,
  packPct,
  ringCircumference,
  ringDashOffset,
} from "../lib/progress-view";

export const Route = createFileRoute("/progress")({
  component: ProgressScreen,
});

function ProgressScreen() {
  const { displayName } = useLogout();
  const progress = useQuery({ queryKey: ["progress"], queryFn: getProgressSummary });
  const packs = useQuery({ queryKey: ["packs"], queryFn: listPacks });

  return (
    <main className="min-h-screen bg-ink px-4 py-5 text-porcelain sm:px-6">
      <div className="mx-auto w-full max-w-[440px]">
        <Link
          className="inline-flex py-2 text-sm font-semibold text-mist hover:text-porcelain"
          to="/"
        >
          ‹ Home
        </Link>

        <AppHeader
          displayName={displayName}
          className="mt-2"
          headingClassName="text-[1.3rem]"
          tagline={
            <p className="mt-2 text-xs uppercase tracking-[0.16em] text-mist">Your progress</p>
          }
        />

        {progress.isPending || packs.isPending ? (
          <p className="mt-8 text-sm text-mist">Loading progress...</p>
        ) : null}
        {progress.isError || packs.isError ? (
          <p className="mt-8 text-sm text-clay">Progress could not be loaded.</p>
        ) : null}

        {progress.data && packs.data ? (
          <ProgressContent progress={progress.data} packs={packs.data} />
        ) : null}
      </div>
    </main>
  );
}

function ProgressContent({
  packs,
  progress,
}: {
  packs: PackSummary[];
  progress: ProgressSummary;
}) {
  const firstIncomplete = packs.find((pack) => packPct(pack.progress) < 100) ?? packs[0];

  return (
    <>
      <GoalRingHero progress={progress} />
      <StatsRow progress={progress} />
      <ActivityCard progress={progress} />
      <NextMilestone progress={progress} />
      <PackProgress packs={packs} />

      {firstIncomplete ? (
        <Link
          className="mt-4 block w-full rounded-md bg-jade px-4 py-3 text-center text-sm font-bold text-ink transition-colors hover:bg-jade-bright"
          params={{ slug: firstIncomplete.slug }}
          to="/packs/$slug"
        >
          Practice now
        </Link>
      ) : null}

      <footer className="pt-8 text-center font-hanzi text-sm text-mist/80">一步一个脚印</footer>
    </>
  );
}

function GoalRingHero({ progress }: { progress: ProgressSummary }) {
  const { completed, target } = progress.daily_goal;
  const remaining = Math.max(0, target - completed);
  const headline =
    remaining === 0
      ? "Goal complete"
      : remaining === 1
        ? "One more to go"
        : `${remaining} more to go`;
  const circumference = ringCircumference();
  const dashOffset = ringDashOffset(completed, target);

  return (
    <section className="mt-4 flex items-center gap-5 rounded-lg border border-white/10 bg-panel p-6 shadow-panel">
      <div className="relative h-[118px] w-[118px] shrink-0">
        <svg aria-hidden="true" className="h-[118px] w-[118px]" viewBox="0 0 118 118">
          <circle cx="59" cy="59" fill="none" r="52" stroke="#22272b" strokeWidth="12" />
          <circle
            cx="59"
            cy="59"
            fill="none"
            r="52"
            stroke="#5fb89a"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            strokeLinecap="round"
            strokeWidth="12"
            style={{ transform: "rotate(-90deg)", transformOrigin: "center" }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <p className="text-3xl font-extrabold leading-none">
            {completed}
            <span className="text-lg text-mist">/{target}</span>
          </p>
          <p className="mt-1 text-[11px] uppercase tracking-[0.08em] text-mist">today</p>
        </div>
      </div>

      <div>
        <h2 className="text-base font-bold">{headline}</h2>
        <p className="mt-2 text-sm leading-relaxed text-mist">
          Finish today's goal to reach a{" "}
          <span className="font-semibold text-jade">{progress.current_streak + 1}-day streak</span>.
        </p>
        <p className="mt-3 inline-flex items-center gap-2 rounded-full border border-jade/30 bg-jade/10 px-3 py-1 text-sm text-jade">
          <span className="font-hanzi">火</span>
          {progress.current_streak}-day streak
        </p>
      </div>
    </section>
  );
}

function StatsRow({ progress }: { progress: ProgressSummary }) {
  const { characters_traced, packs_completed, packs_total } = progress;

  return (
    <section className="mt-4 grid grid-cols-2 gap-3" data-testid="progress-stats-row">
      <StatTile label="Characters" value={characters_traced} />
      <StatTile label="Packs" value={`${packs_completed}/${packs_total}`} />
    </section>
  );
}

function StatTile({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-lg border border-white/10 bg-panel p-4">
      <p className="text-2xl font-extrabold leading-none">{value}</p>
      <p className="mt-1.5 text-xs uppercase tracking-[0.08em] text-mist">{label}</p>
    </div>
  );
}

function ActivityCard({ progress }: { progress: ProgressSummary }) {
  const [expanded, setExpanded] = useState(false);
  const strip = last14(progress.activity);
  const month = currentMonth(progress.activity);

  return (
    <button
      aria-expanded={expanded}
      className="mt-4 block w-full rounded-lg border border-white/10 bg-panel p-4 text-left transition-colors hover:border-jade/30"
      onClick={() => setExpanded((current) => !current)}
      type="button"
    >
      <span className="flex items-center justify-between gap-3">
        <span className="text-[15px] font-semibold">Activity</span>
        <span className="flex items-center gap-2 text-xs text-mist">
          {expanded ? "Tap to collapse" : "Tap to expand"}
          <span className="text-jade" aria-hidden="true">
            {expanded ? "▲" : "▼"}
          </span>
        </span>
      </span>

      {expanded ? (
        <span className="mt-4 block">
          <span className="mb-2.5 flex items-center justify-between text-xs text-mist">
            <span>This month</span>
            <span>{month.activeDays} active days</span>
          </span>
          <span className="grid grid-flow-col grid-rows-7 justify-start gap-[5px]">
            {month.cells.map((day, index) => (
              <span
                aria-label={day.date ? `${day.date}: ${day.count} completions` : "empty"}
                className={`h-3 w-3 rounded-[3px] ${heatmapLevelClass(day.level)}`}
                data-level={day.level}
                key={day.date ?? `blank-${index}`}
                title={day.date ?? ""}
              />
            ))}
          </span>
          <span className="mt-3 flex items-center justify-end gap-1.5 text-[11px] text-mist">
            <span>Less</span>
            {[0, 1, 2, 3].map((level) => (
              <span
                className={`h-2.5 w-2.5 rounded-[3px] ${heatmapLevelClass(level)}`}
                data-level={level}
                key={level}
              />
            ))}
            <span>More</span>
          </span>
        </span>
      ) : (
        <span className="mt-4 block">
          <span className="flex gap-[5px]">
            {strip.map((day) => (
              <span
                aria-label={`${day.date}: ${day.count} completions`}
                className={`aspect-square flex-1 rounded-[3px] ${heatmapLevelClass(day.level)}`}
                data-level={day.level}
                key={day.date}
                title={day.date}
              />
            ))}
          </span>
          <span className="mt-2.5 block text-xs text-mist">
            Last 14 days · {progress.current_streak}-day streak
          </span>
        </span>
      )}
    </button>
  );
}

function NextMilestone({ progress }: { progress: ProgressSummary }) {
  const milestone = progress.next_milestone;

  return (
    <section className="mt-4 rounded-lg border border-white/10 bg-panel p-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-[15px] font-semibold">Next milestone</h2>
        <p className="text-sm text-brass">{milestone.target_days}-day streak</p>
      </div>
      <div className="mt-4 h-2 rounded-full bg-panel2">
        <div
          className="h-2 rounded-full bg-brass"
          style={{ width: `${milestone.progress_pct}%` }}
        />
      </div>
      <p className="mt-2.5 text-xs text-mist">
        {milestone.days_remaining} {milestone.days_remaining === 1 ? "day" : "days"} away - you've
        got this.
      </p>
    </section>
  );
}

function PackProgress({ packs }: { packs: PackSummary[] }) {
  return (
    <section className="mt-4 rounded-lg border border-white/10 bg-panel p-4">
      <h2 className="text-[15px] font-semibold">Pack progress</h2>
      <div className="mt-4 space-y-3.5">
        {packs.map((pack) => {
          const percent = packPct(pack.progress);
          return (
            <div className="grid grid-cols-[38px_1fr] items-center gap-3" key={pack.slug}>
              <span
                className="flex h-[38px] w-[38px] items-center justify-center rounded-[9px] font-hanzi text-xl"
                style={{ backgroundColor: `${pack.color}22`, color: pack.color }}
              >
                {pack.glyph}
              </span>
              <span className="min-w-0">
                <span className="flex items-center justify-between gap-3">
                  <span className="truncate text-sm font-semibold">{pack.title}</span>
                  <span className="text-xs text-mist">{percent}%</span>
                </span>
                <span className="mt-1.5 block h-1.5 rounded-full bg-panel2">
                  <span
                    className="block h-1.5 rounded-full"
                    style={{ backgroundColor: pack.color, width: `${percent}%` }}
                  />
                </span>
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
