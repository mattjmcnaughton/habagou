import { describe, expect, it } from "vitest";
import {
  currentMonth,
  heatmapLevelClass,
  last14,
  packPct,
  ringCircumference,
  ringDashOffset,
} from "./progress-view";

describe("progress view helpers", () => {
  it("takes the last fourteen activity days", () => {
    const activity = Array.from({ length: 45 }, (_, index) => ({
      date: `2026-07-${String(index + 1).padStart(2, "0")}`,
      count: index,
      level: Math.min(index, 3),
    }));

    expect(last14(activity).map((day) => day.date)).toEqual(
      activity.slice(-14).map((day) => day.date),
    );
  });

  it("builds the current month grid and active-day count", () => {
    const activity = [
      { date: "2026-07-01", count: 1, level: 1 },
      { date: "2026-07-03", count: 3, level: 3 },
      { date: "2026-06-30", count: 3, level: 3 },
    ];

    const month = currentMonth(activity, new Date(2026, 6, 5));

    expect(month.activeDays).toBe(2);
    expect(month.cells.filter((cell) => cell.date === null)).toHaveLength(3);
    expect(month.cells[month.cells.length - 1]).toMatchObject({
      date: "2026-07-05",
      count: 0,
      level: 0,
    });
  });

  it("computes the goal ring dash offset", () => {
    expect(ringDashOffset(2, 3)).toBeCloseTo(ringCircumference() / 3);
    expect(ringDashOffset(3, 3)).toBe(0);
    expect(ringDashOffset(5, 3)).toBe(0);
  });

  it("converts pack completion to display percent", () => {
    expect(
      packPct({
        trace: { completed: false, completion_count: 0, best_duration_ms: null },
        match: { completed: false, completion_count: 0, best_duration_ms: null },
        sentence: { completed: false, completion_count: 0, best_duration_ms: null },
      }),
    ).toBe(0);
    expect(
      packPct({
        trace: { completed: true, completion_count: 1, best_duration_ms: 1000 },
        match: { completed: true, completion_count: 1, best_duration_ms: 1000 },
        sentence: { completed: false, completion_count: 0, best_duration_ms: null },
      }),
    ).toBe(67);
  });

  it("maps heatmap levels to token classes", () => {
    expect(heatmapLevelClass(0)).toBe("bg-panel2");
    expect(heatmapLevelClass(1)).toBe("bg-jade/35");
    expect(heatmapLevelClass(2)).toBe("bg-jade/65");
    expect(heatmapLevelClass(3)).toBe("bg-jade");
  });
});
