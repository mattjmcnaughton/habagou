import type { PathActivity, PathItem } from "../lib/api";

// A single lesson node: spine dot (keyed to state) + activity card.

const ACTIVITY_LABEL: Record<PathActivity, string> = {
  trace: "Trace",
  match: "Match",
  sentence: "Sentence",
};

const ACTIVITY_ICON: Record<PathActivity, string> = {
  trace: "✎",
  match: "⧉",
  sentence: "☰",
};

export function activityLabel(activity: PathActivity): string {
  return ACTIVITY_LABEL[activity];
}

// Character sub-line pulled from the item content (hanzi joined by spaces).
export function nodeHanziLine(item: PathItem): string {
  if (item.activity === "trace" && item.content.trace) {
    return item.content.trace.chars.map((char) => char.hanzi).join(" ");
  }
  if (item.activity === "match" && item.content.match) {
    return item.content.match.pairs.map((pair) => pair.hanzi).join(" ");
  }
  if (item.activity === "sentence" && item.content.sentence) {
    return item.content.sentence.hanzi;
  }
  return "";
}

function SpineDot({ item }: { item: PathItem }) {
  const color = item.pack.color;
  if (item.state === "done") {
    return (
      <span
        aria-hidden="true"
        className="absolute left-[18px] top-[22px] h-4 w-4 rounded-full"
        data-state="done"
        data-testid="path-node-dot"
        style={{ backgroundColor: color, boxShadow: "0 0 0 4px #0e0f11" }}
      />
    );
  }
  if (item.state === "current") {
    return (
      <span
        aria-hidden="true"
        className="absolute left-[18px] top-[22px] h-4 w-4 rounded-full"
        data-state="current"
        data-testid="path-node-dot"
        style={{
          backgroundColor: "#0e0f11",
          border: `3px solid ${color}`,
          boxShadow: `0 0 0 4px #0e0f11, 0 0 0 8px ${color}2e`,
        }}
      />
    );
  }
  return (
    <span
      aria-hidden="true"
      className="absolute left-[20px] top-[24px] h-3 w-3 rounded-full border-2 border-[#2b3236] bg-panel2"
      data-state="locked"
      data-testid="path-node-dot"
    />
  );
}

function KindChip({ kind }: { kind: PathItem["kind"] }) {
  if (kind === "review") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-jade/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.04em] text-jade-bright">
        ↻ Review
      </span>
    );
  }
  return (
    <span className="inline-flex items-center rounded-full bg-white/5 px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.04em] text-mist">
      New
    </span>
  );
}

export function PathNode({ item }: { item: PathItem }) {
  const color = item.pack.color;
  const isCurrent = item.state === "current";
  const isLocked = item.state === "locked";
  const title = `${activityLabel(item.activity)} · ${item.pack.title} ${item.pack.glyph}`;
  const hanziLine = nodeHanziLine(item);

  const cardStyle = isCurrent
    ? {
        backgroundColor: "#1b1f22",
        border: `1px solid ${color}`,
        boxShadow: `0 0 0 3px ${color}22, 0 14px 40px rgba(0,0,0,0.32)`,
      }
    : { backgroundColor: "#181b1e" };

  return (
    <div className="relative pb-4 pl-[54px]" data-state={item.state} data-testid="path-node">
      <SpineDot item={item} />
      <div
        className={`flex flex-col gap-3 rounded-2xl border border-white/10 p-3 ${
          isLocked ? "opacity-60" : ""
        }`}
        style={cardStyle}
      >
        <div className="flex items-center gap-3">
          <span
            aria-hidden="true"
            className="flex h-[42px] w-[42px] shrink-0 items-center justify-center rounded-xl text-[19px]"
            style={{ backgroundColor: `${color}26`, color }}
          >
            {ACTIVITY_ICON[item.activity]}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-bold">
              {activityLabel(item.activity)}{" "}
              <span className="font-normal text-mist">· {item.pack.title}</span>{" "}
              <span className="font-hanzi" style={{ color }}>
                {item.pack.glyph}
              </span>
            </p>
            {hanziLine ? (
              <p className="mt-0.5 truncate font-hanzi text-[13px] text-[#7a848a]">{hanziLine}</p>
            ) : null}
          </div>
          <div className="flex shrink-0 flex-col items-end gap-1.5">
            <KindChip kind={item.kind} />
            {item.state === "done" ? (
              <span aria-label="completed" className="text-sm text-jade-bright" role="img">
                ✓
              </span>
            ) : null}
          </div>
        </div>

        {isCurrent ? (
          <a
            className="block w-full rounded-xl px-4 py-2.5 text-center text-sm font-extrabold text-ink transition-opacity hover:opacity-90"
            href={`/lesson/${item.id}`}
            style={{ backgroundColor: color }}
          >
            Start lesson →
          </a>
        ) : null}
      </div>
      <span className="sr-only">{title}</span>
    </div>
  );
}
