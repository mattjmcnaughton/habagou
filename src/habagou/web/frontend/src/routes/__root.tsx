import { Link, Outlet, createRootRoute } from "@tanstack/react-router";

export const Route = createRootRoute({
  component: () => <Outlet />,
  errorComponent: () => (
    <main className="min-h-screen bg-ink px-4 py-5 text-porcelain sm:px-6">
      <div className="mx-auto flex min-h-[calc(100vh-2.5rem)] w-full max-w-[440px] flex-col justify-center">
        <section className="rounded-lg border border-clay/40 bg-panel p-6 text-center shadow-panel">
          <h1 className="text-2xl font-bold text-clay">Something went wrong.</h1>
          <Link
            className="mt-6 inline-flex w-full justify-center rounded-md bg-jade px-4 py-3 text-sm font-bold text-ink transition-colors hover:bg-jade-bright"
            to="/"
          >
            Back to packs
          </Link>
        </section>
      </div>
    </main>
  ),
});
