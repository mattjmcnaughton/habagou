import { type ReactNode, useEffect, useRef, useState } from "react";

// Shared app-shell header: wordmark + optional tagline, with the learner's
// account tucked behind a single avatar. On screens that pass `onLogout` (Path,
// Packs) the avatar opens a small menu with the identity and a Sign out action;
// on display-only screens (Progress) it falls back to a static identity chip.
// Collapsing the old email-pill + Sign out cluster into one control keeps the
// wordmark from being squeezed into a second line.

function initialsFor(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) {
    return "?";
  }
  if (parts.length === 1) {
    return parts[0].slice(0, 2).toUpperCase();
  }
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function AppHeader({
  displayName,
  onLogout,
  tagline,
  headingClassName = "text-[1.45rem]",
  className = "",
}: {
  displayName: string;
  onLogout?: () => void;
  tagline?: ReactNode;
  headingClassName?: string;
  className?: string;
}) {
  return (
    <header className={`flex items-start justify-between gap-4 ${className}`.trimEnd()}>
      <div className="min-w-0">
        <div className="flex items-baseline gap-2">
          <h1 className={`${headingClassName} font-bold leading-none tracking-normal`}>Habagou</h1>
          <span className="font-hanzi text-lg text-jade">哈巴狗</span>
        </div>
        {tagline}
      </div>
      {onLogout ? (
        <AccountMenu displayName={displayName} onLogout={onLogout} />
      ) : (
        <div className="flex h-8 max-w-[8rem] shrink-0 items-center gap-2 rounded-full border border-white/10 bg-panel px-3 text-sm text-mist">
          <span className="h-2 w-2 shrink-0 rounded-full bg-jade" />
          <span className="truncate">{displayName}</span>
        </div>
      )}
    </header>
  );
}

function AccountMenu({ displayName, onLogout }: { displayName: string; onLogout: () => void }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  // Close on an outside click or Escape while open — a lightweight popover, so
  // it owns these listeners itself rather than pulling in a menu primitive.
  useEffect(() => {
    if (!open) {
      return;
    }
    function onPointerDown(event: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="relative shrink-0" ref={wrapRef}>
      <button
        aria-expanded={open}
        aria-haspopup="true"
        aria-label={`Account: ${displayName}`}
        className="relative flex h-10 w-10 items-center justify-center rounded-full border border-white/10 bg-panel text-sm font-bold text-jade transition-colors hover:border-white/25"
        onClick={() => setOpen((value) => !value)}
        type="button"
      >
        {initialsFor(displayName)}
        <span
          aria-hidden="true"
          className="absolute bottom-0 right-0 h-2.5 w-2.5 rounded-full border-2 border-ink bg-jade"
        />
      </button>
      {open ? (
        <div className="absolute right-0 top-12 z-50 w-56 rounded-2xl border border-white/10 bg-panel2 p-1.5 shadow-panel">
          <div className="border-b border-white/5 px-3 pb-3 pt-2">
            <p className="text-[0.65rem] font-semibold uppercase tracking-[0.14em] text-mist">
              Signed in
            </p>
            <p className="mt-1 truncate text-sm font-semibold text-porcelain">{displayName}</p>
          </div>
          <button
            className="mt-1.5 flex w-full items-center rounded-lg px-3 py-2.5 text-left text-sm text-porcelain transition-colors hover:bg-white/[0.05]"
            onClick={() => {
              setOpen(false);
              onLogout();
            }}
            type="button"
          >
            Sign out
          </button>
        </div>
      ) : null}
    </div>
  );
}
