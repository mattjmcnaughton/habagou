import type { ReactNode } from "react";

// Shared app-shell header: wordmark + learner pill, with an optional tagline
// slot and an optional Sign out button (omitted on screens that only display
// the learner, like Progress).

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
      <div>
        <div className="flex items-baseline gap-2">
          <h1 className={`${headingClassName} font-bold leading-none tracking-normal`}>Habagou</h1>
          <span className="font-hanzi text-lg text-jade">哈巴狗</span>
        </div>
        {tagline}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <div className="flex h-8 max-w-[8rem] items-center gap-2 rounded-full border border-white/10 bg-panel px-3 text-sm text-mist">
          <span className="h-2 w-2 shrink-0 rounded-full bg-jade" />
          <span className="truncate">{displayName}</span>
        </div>
        {onLogout ? (
          <button
            className="h-8 rounded-md border border-white/10 bg-panel px-3 text-sm text-mist transition-colors hover:border-clay/40 hover:text-porcelain"
            onClick={onLogout}
            type="button"
          >
            Sign out
          </button>
        ) : null}
      </div>
    </header>
  );
}
