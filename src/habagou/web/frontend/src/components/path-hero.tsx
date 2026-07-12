import type { DailyGoal, PathDue } from "../lib/api";
import { PathGoalRing } from "./path-goal-ring";

// Path hero goal card: goal ring + headline + streak/due chips.

function headlineFor(daily: DailyGoal): string {
  const remaining = Math.max(0, daily.target - daily.completed);
  if (remaining === 0) {
    return "Daily goal complete — keep going!";
  }
  return `${remaining} ${remaining === 1 ? "lesson" : "lessons"} to today's goal`;
}

function dueLabel(due: PathDue): string {
  return `Due · ${due.new} new, ${due.review} ${due.review === 1 ? "review" : "reviews"}`;
}

export function PathHero({
  daily,
  streak,
  due,
}: {
  daily: DailyGoal;
  streak: number;
  due: PathDue;
}) {
  return (
    <section className="mt-6 flex items-center gap-4 rounded-2xl border border-white/10 bg-panel p-3.5 shadow-panel">
      <PathGoalRing completed={daily.completed} target={daily.target} />
      <div className="min-w-0">
        <h2 className="text-[15px] font-bold leading-snug">{headlineFor(daily)}</h2>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-jade/30 bg-jade/10 px-2.5 py-1 text-xs font-semibold text-jade">
            <span className="font-hanzi">火</span>
            {streak}-day
          </span>
          <span className="inline-flex items-center rounded-full border border-white/10 bg-panel2 px-2.5 py-1 text-xs text-mist">
            {dueLabel(due)}
          </span>
        </div>
      </div>
    </section>
  );
}
