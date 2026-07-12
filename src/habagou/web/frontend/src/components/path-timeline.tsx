import type { PathItem } from "../lib/api";
import { PathNode } from "./path-node";

// Vertical timeline: a 2px spine at left ~26px, unit-divider pills, lesson nodes.

function UnitDivider({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3 py-3" data-testid="path-unit-divider">
      <span className="rounded-full border border-white/10 bg-ink px-3 py-[5px] text-[11px] font-extrabold uppercase tracking-[0.12em] text-mist">
        {label}
      </span>
      <span aria-hidden="true" className="h-px flex-1 bg-white/10" />
    </div>
  );
}

export function PathTimeline({ items }: { items: PathItem[] }) {
  return (
    <div className="relative mt-6" data-testid="path-timeline">
      <span aria-hidden="true" className="absolute bottom-0 left-[26px] top-0 w-0.5 bg-panel2" />
      <div className="relative">
        {items.map((item) => (
          <div key={item.id}>
            {item.unit_label ? <UnitDivider label={item.unit_label} /> : null}
            <PathNode item={item} />
          </div>
        ))}
      </div>
    </div>
  );
}
