import { Link } from "@tanstack/react-router";

type Tab = {
  to: "/" | "/packs" | "/practice" | "/progress";
  label: string;
  glyph: string;
  isActive: (pathname: string) => boolean;
};

const TABS: Tab[] = [
  { to: "/", label: "Path", glyph: "◈", isActive: (pathname) => pathname === "/" },
  {
    to: "/packs",
    label: "Packs",
    glyph: "▦",
    // "Packs" stays active on the library, pack detail, and whole-pack activities.
    isActive: (pathname) => pathname === "/packs" || pathname.startsWith("/packs/"),
  },
  {
    to: "/practice",
    label: "Practice",
    glyph: "讠",
    isActive: (pathname) => pathname === "/practice" || pathname.startsWith("/practice/"),
  },
  {
    to: "/progress",
    label: "Progress",
    glyph: "◑",
    isActive: (pathname) => pathname === "/progress" || pathname.startsWith("/progress/"),
  },
];

/**
 * Returns true when the persistent bottom tab bar should be hidden for the given
 * path: whole-pack activity routes (trace/match/sentence), future /lesson/*
 * routes (and their done screens), and /login. The Path shell, pack library,
 * pack detail, and Progress all keep the tab bar.
 */
export function isTabBarHidden(pathname: string): boolean {
  if (pathname === "/login") {
    return true;
  }
  if (pathname === "/lesson" || pathname.startsWith("/lesson/")) {
    return true;
  }
  if (/^\/packs\/[^/]+\/(trace|match|sentence)\/?$/.test(pathname)) {
    return true;
  }
  return false;
}

export function TabBar({ pathname }: { pathname: string }) {
  return (
    <nav
      aria-label="Primary"
      className="fixed inset-x-0 bottom-0 z-40 h-[62px] border-t border-white/10 bg-ink/80 backdrop-blur-md"
    >
      <div className="mx-auto flex h-full max-w-[440px] items-stretch">
        {TABS.map((tab) => {
          const active = tab.isActive(pathname);
          return (
            <Link
              aria-current={active ? "page" : undefined}
              className="relative flex flex-1 flex-col items-center justify-center gap-1"
              key={tab.to}
              to={tab.to}
            >
              {active ? (
                <span
                  aria-hidden="true"
                  className="absolute top-0 h-0.5 w-8 rounded-full bg-jade"
                />
              ) : null}
              <span
                aria-hidden="true"
                className={`text-lg leading-none ${active ? "text-jade" : "text-mist"}`}
              >
                {tab.glyph}
              </span>
              <span className={`text-xs ${active ? "text-jade" : "text-mist"}`}>{tab.label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
