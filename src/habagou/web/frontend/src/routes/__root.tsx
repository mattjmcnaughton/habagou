import {
  Link,
  Outlet,
  createRootRouteWithContext,
  redirect,
  useRouterState,
} from "@tanstack/react-router";
import type { RouterContext } from "../app/app";
import { TabBar, isTabBarHidden } from "../components/tab-bar";
import { getAuthSession } from "../lib/api";

export const Route = createRootRouteWithContext<RouterContext>()({
  beforeLoad: async ({ context, location }) => {
    const session = await context.queryClient.ensureQueryData({
      queryKey: ["auth", "session"],
      queryFn: getAuthSession,
    });
    if (!session.authenticated && location.pathname !== "/login") {
      throw redirect({ to: "/login" });
    }
  },
  component: RootLayout,
  errorComponent: () => (
    <main className="min-h-screen bg-ink px-4 py-5 text-porcelain sm:px-6">
      <div className="mx-auto flex min-h-[calc(100vh-2.5rem)] w-full max-w-[440px] flex-col justify-center">
        <section className="rounded-lg border border-clay/40 bg-panel p-6 text-center shadow-panel">
          <h1 className="text-2xl font-bold text-clay">Something went wrong.</h1>
          <Link
            className="mt-6 inline-flex w-full justify-center rounded-md bg-jade px-4 py-3 text-sm font-bold text-ink transition-colors hover:bg-jade-bright"
            to="/"
          >
            Back to Path
          </Link>
        </section>
      </div>
    </main>
  ),
});

function RootLayout() {
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const showTabBar = !isTabBarHidden(pathname);

  return (
    <>
      <div className={showTabBar ? "pb-[62px]" : undefined}>
        <Outlet />
      </div>
      {showTabBar ? <TabBar pathname={pathname} /> : null}
    </>
  );
}
