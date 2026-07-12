import { useInfiniteQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { AppHeader } from "../components/app-header";
import { PathHero } from "../components/path-hero";
import { PathLoadMore } from "../components/path-load-more";
import { PathTimeline } from "../components/path-timeline";
import { useLogout } from "../components/use-logout";
import { getPath, PATH_PAGE_LIMIT } from "../lib/api";
import type { PathResponse } from "../lib/api";

export const Route = createFileRoute("/")({
  component: PathScreen,
});

function PathScreen() {
  const { displayName, handleLogout } = useLogout();

  const path = useInfiniteQuery({
    queryKey: ["path"],
    queryFn: ({ pageParam }) => getPath({ cursor: pageParam, limit: PATH_PAGE_LIMIT }),
    initialPageParam: 0,
    getNextPageParam: (lastPage: PathResponse) => lastPage.next_cursor ?? undefined,
  });

  const firstPage = path.data?.pages[0];
  const items = path.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <main className="min-h-screen bg-ink px-4 py-5 text-porcelain sm:px-6" data-testid="path-shell">
      <div className="mx-auto flex min-h-[calc(100vh-2.5rem)] w-full max-w-[440px] flex-col">
        <AppHeader displayName={displayName} onLogout={() => void handleLogout()} />

        {firstPage ? (
          <PathHero daily={firstPage.daily} streak={firstPage.streak} due={firstPage.due} />
        ) : null}

        {path.isPending ? <p className="mt-8 text-sm text-mist">Loading your path...</p> : null}
        {path.isError ? (
          <p className="mt-8 text-sm text-clay">Your path could not be loaded.</p>
        ) : null}

        {items.length > 0 ? <PathTimeline items={items} /> : null}

        {firstPage ? (
          <PathLoadMore
            hasMore={path.hasNextPage}
            isFetching={path.isFetchingNextPage}
            onLoadMore={() => void path.fetchNextPage()}
          />
        ) : null}
      </div>
    </main>
  );
}
