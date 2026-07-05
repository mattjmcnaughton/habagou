import type { PackSummary, ProgressSummary } from "./api";

export type DailyActivity = ProgressSummary["activity"][number];

export type MonthCell = {
  date: string | null;
  count: number;
  level: number;
};

const RING_CIRCUMFERENCE = 2 * Math.PI * 52;

export function last14(activity: DailyActivity[]): DailyActivity[] {
  return activity.slice(-14);
}

export function currentMonth(activity: DailyActivity[], today = new Date()) {
  const todayKey = toLocalDateKey(today);
  const monthPrefix = todayKey.slice(0, 7);
  const byDate = new Map(activity.map((day) => [day.date, day]));
  const firstOfMonth = new Date(today.getFullYear(), today.getMonth(), 1);
  const cells: MonthCell[] = Array.from({ length: firstOfMonth.getDay() }, () => ({
    date: null,
    count: 0,
    level: 0,
  }));

  for (let day = 1; day <= today.getDate(); day += 1) {
    const key = toLocalDateKey(new Date(today.getFullYear(), today.getMonth(), day));
    const activityDay = byDate.get(key);
    cells.push({
      date: key,
      count: activityDay?.count ?? 0,
      level: activityDay?.level ?? 0,
    });
  }

  return {
    cells,
    activeDays: activity.filter((day) => day.date.startsWith(monthPrefix) && day.count > 0).length,
  };
}

export function ringDashOffset(completed: number, target: number): number {
  if (target <= 0) {
    return RING_CIRCUMFERENCE;
  }
  const progress = Math.max(0, Math.min(1, completed / target));
  return RING_CIRCUMFERENCE * (1 - progress);
}

export function ringCircumference(): number {
  return RING_CIRCUMFERENCE;
}

export function packPct(progress: PackSummary["progress"]): number {
  const completed = [progress.trace, progress.match, progress.sentence].filter(
    (activity) => activity.completed,
  ).length;
  return Math.round((completed / 3) * 100);
}

export function heatmapLevelClass(level: number): string {
  if (level <= 0) {
    return "bg-panel2";
  }
  if (level === 1) {
    return "bg-jade/35";
  }
  if (level === 2) {
    return "bg-jade/65";
  }
  return "bg-jade";
}

function toLocalDateKey(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}
