import { useQuery } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect } from "react";
import { getAuthSession } from "../lib/api";

export const Route = createFileRoute("/login")({
  component: Login,
});

function Login() {
  const navigate = useNavigate();
  const session = useQuery({ queryKey: ["auth", "session"], queryFn: getAuthSession });
  const hasError = new URLSearchParams(window.location.search).get("error") === "auth_failed";

  useEffect(() => {
    if (session.data?.authenticated) {
      const timer = window.setTimeout(() => void navigate({ to: "/" }), 600);
      return () => window.clearTimeout(timer);
    }
    return undefined;
  }, [navigate, session.data?.authenticated]);

  return (
    <main className="min-h-screen bg-ink px-4 py-5 text-porcelain sm:px-6">
      <div className="mx-auto flex min-h-[calc(100vh-2.5rem)] w-full max-w-[440px] flex-col justify-center">
        <section className="rounded-lg border border-clay/40 bg-panel p-6 text-center shadow-panel">
          <div className="flex items-baseline justify-center gap-2">
            <h1 className="text-[1.45rem] font-bold leading-none tracking-normal">Habagou</h1>
            <span className="font-hanzi text-lg text-jade">哈巴狗</span>
          </div>
          <p className="mt-3 text-base leading-6 text-mist">
            Learn to write Chinese characters, stroke by stroke.
          </p>

          {session.data?.authenticated ? (
            <SignedInState username={session.data.user?.username ?? "learner"} />
          ) : (
            <>
              <div className="mx-auto mt-8 flex h-[120px] w-[120px] items-center justify-center rounded-lg border border-jade/50 bg-ink font-hanzi text-7xl text-jade shadow-panel">
                门
              </div>
              <h2 className="mt-7 text-2xl font-bold leading-tight">Sign in to keep your streak</h2>
              <p className="mx-auto mt-3 max-w-[19rem] text-sm leading-6 text-mist">
                Your progress syncs across devices when you log in.
              </p>
              {hasError ? (
                <p className="mt-5 rounded-md border border-clay/40 bg-clay/10 px-3 py-2 text-sm text-clay">
                  Sign-in didn&apos;t complete. Try again.
                </p>
              ) : null}
              <a
                className="mt-6 inline-flex w-full items-center justify-center rounded-md border border-white/15 bg-ink px-4 py-3 text-sm font-bold text-porcelain transition hover:-translate-y-0.5 hover:border-jade/40 hover:bg-white/[0.04]"
                href="/auth/login"
              >
                Continue with Keycloak (dev)
              </a>
              <p className="mx-auto mt-4 max-w-[18rem] text-xs leading-5 text-mist">
                We only read your public profile and email. No repos, no writes.
              </p>
            </>
          )}
        </section>

        <footer className="pt-8 text-center font-hanzi text-sm text-mist/80">一笔一画</footer>
      </div>
    </main>
  );
}

function SignedInState({ username }: { username: string }) {
  return (
    <>
      <div className="mx-auto mt-8 flex h-[120px] w-[120px] items-center justify-center rounded-lg border border-jade/50 bg-jade/10 text-5xl text-jade shadow-panel">
        ✓
      </div>
      <h2 className="mt-7 text-2xl font-bold leading-tight">Welcome back</h2>
      <p className="mx-auto mt-3 max-w-[19rem] text-sm leading-6 text-mist">
        Signed in as @{username}. Taking you to your packs...
      </p>
      <a
        className="mt-6 inline-flex w-full justify-center rounded-md bg-jade px-4 py-3 text-sm font-bold text-ink transition-colors hover:bg-jade-bright"
        href="/"
      >
        Enter Habagou
      </a>
    </>
  );
}
