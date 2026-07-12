// Goal ring for the Path hero: ~68px SVG (viewBox 0 0 92 92), panel2 track,
// jade progress with a round line cap, center "done/goal" label. Mirrors the
// GoalRingHero ring in routes/progress.tsx, sized down for the hero card.

import { ringCircumference, ringDashOffset } from "../lib/progress-view";

const RADIUS = 40;

export function PathGoalRing({ completed, target }: { completed: number; target: number }) {
  return (
    <div className="relative h-[68px] w-[68px] shrink-0">
      <svg aria-hidden="true" className="h-[68px] w-[68px]" viewBox="0 0 92 92">
        <circle cx="46" cy="46" fill="none" r={RADIUS} stroke="#22272b" strokeWidth="10" />
        <circle
          cx="46"
          cy="46"
          fill="none"
          r={RADIUS}
          stroke="#5fb89a"
          strokeDasharray={ringCircumference(RADIUS)}
          strokeDashoffset={ringDashOffset(completed, target, RADIUS)}
          strokeLinecap="round"
          strokeWidth="10"
          style={{ transform: "rotate(-90deg)", transformOrigin: "center" }}
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <p className="text-lg font-extrabold leading-none" data-testid="path-goal-ring-label">
          {completed}
          <span className="text-mist">/{target}</span>
        </p>
      </div>
    </div>
  );
}
