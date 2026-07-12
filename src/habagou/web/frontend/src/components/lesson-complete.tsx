import { Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";

// Done screen for a Path lesson (design 06-lesson-complete). Jade check pops in
// on mount, followed by a title, a completion pill, and the Back to Path CTA.
// Learners are always signed in, so the pill reads "Completion recorded" with no
// guest wording.

export type LessonCompleteStatus = "recording" | "recorded" | "error";

type LessonCompleteProps = {
  status: LessonCompleteStatus;
  onRetry?: () => void;
};

export function LessonComplete({ status, onRetry }: LessonCompleteProps) {
  const [popped, setPopped] = useState(false);

  useEffect(() => {
    const frame = requestAnimationFrame(() => setPopped(true));
    return () => cancelAnimationFrame(frame);
  }, []);

  return (
    <main className="min-h-screen bg-ink px-4 py-5 text-porcelain sm:px-6">
      <div className="mx-auto flex min-h-[calc(100vh-2.5rem)] w-full max-w-[440px] flex-col justify-center">
        <section className="rounded-lg border border-white/10 bg-panel p-6 text-center shadow-panel">
          <div
            className={`mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-jade/15 text-4xl text-jade transition-all duration-300 ease-out ${
              popped ? "scale-100 opacity-100" : "scale-50 opacity-0"
            }`}
            data-testid="lesson-complete-check"
          >
            ✓
          </div>
          <h1 className="mt-5 text-2xl font-bold">Lesson complete!</h1>

          {status === "recorded" ? (
            <p className="mt-4">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-jade/30 bg-jade/10 px-3 py-1 text-sm text-jade">
                ✓ Completion recorded
              </span>
            </p>
          ) : null}

          {status === "recording" ? (
            <p className="mt-4 text-sm text-mist">Recording completion...</p>
          ) : null}

          {status === "error" ? (
            <div className="mt-4" role="alert">
              <p className="text-sm text-clay">Completion could not be recorded.</p>
              {onRetry ? (
                <button
                  className="mt-3 rounded-md border border-clay/40 px-3 py-2 text-sm font-semibold text-porcelain transition-colors hover:bg-clay/10"
                  onClick={onRetry}
                  type="button"
                >
                  Retry recording
                </button>
              ) : null}
            </div>
          ) : null}

          <Link
            className="mt-6 inline-flex w-full justify-center rounded-md bg-jade px-4 py-3 text-sm font-bold text-ink transition-colors hover:bg-jade-bright"
            to="/"
          >
            Back to Path
          </Link>
        </section>
      </div>
    </main>
  );
}
