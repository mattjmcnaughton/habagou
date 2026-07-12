import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { InfiniteData } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { LessonComplete, type LessonCompleteStatus } from "../components/lesson-complete";
import { MatchRunner } from "../components/match-runner";
import { SentenceRunner } from "../components/sentence-runner";
import { TraceRunner } from "../components/trace-runner";
import { ApiError, completePathItem, getPath, PATH_PAGE_LIMIT } from "../lib/api";
import type { PathItem, PathResponse } from "../lib/api";

export const Route = createFileRoute("/lesson/$itemId")({
  component: LessonRunner,
});

// Resolve a PathItem by id: prefer the already-cached ["path"] infinite pages
// (the Path screen populates them), and only hit the network on a deep link or
// hard refresh, walking pages until the item is found or the Path is exhausted.
async function resolvePathItem(
  queryClient: ReturnType<typeof useQueryClient>,
  itemId: string,
): Promise<PathItem | null> {
  const cached = queryClient.getQueryData<InfiniteData<PathResponse>>(["path"]);
  const fromCache = cached?.pages.flatMap((page) => page.items).find((item) => item.id === itemId);
  if (fromCache) {
    return fromCache;
  }

  let cursor: number | undefined = 0;
  while (cursor !== undefined) {
    const page: PathResponse = await getPath({ cursor, limit: PATH_PAGE_LIMIT });
    const found = page.items.find((item) => item.id === itemId);
    if (found) {
      return found;
    }
    cursor = page.next_cursor ?? undefined;
  }
  return null;
}

function LessonRunner() {
  const { itemId } = Route.useParams();
  const queryClient = useQueryClient();
  const startedAt = useRef(Date.now());
  const [finished, setFinished] = useState(false);

  const item = useQuery({
    queryKey: ["lesson", "item", itemId],
    queryFn: () => resolvePathItem(queryClient, itemId),
  });

  const completion = useMutation({
    mutationFn: () =>
      completePathItem(itemId, { duration_ms: Math.max(0, Date.now() - startedAt.current) }),
    onSuccess: () => invalidatePath(),
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409) {
        invalidatePath();
      }
    },
  });

  useEffect(() => {
    startedAt.current = Date.now();
  }, []);

  function invalidatePath() {
    void queryClient.invalidateQueries({ queryKey: ["path"] });
    void queryClient.invalidateQueries({ queryKey: ["progress"] });
  }

  function handleFinish() {
    setFinished(true);
    if (completion.isIdle) {
      completion.mutate();
    }
  }

  // A 409 (already completed) is a success for the learner: the item is done.
  const alreadyCompleted =
    completion.isError && completion.error instanceof ApiError && completion.error.status === 409;

  if (finished) {
    let status: LessonCompleteStatus = "recording";
    if (completion.isSuccess || alreadyCompleted) {
      status = "recorded";
    } else if (completion.isError) {
      status = "error";
    }
    return <LessonComplete status={status} onRetry={() => completion.mutate()} />;
  }

  if (item.isPending) {
    return <LessonShell>Loading lesson...</LessonShell>;
  }

  if (item.isError) {
    return <LessonShell>This lesson could not be loaded.</LessonShell>;
  }

  if (!item.data) {
    return <LessonShell>We could not find this lesson.</LessonShell>;
  }

  const backLink = <PathBackLink />;
  const content = item.data.content;

  if (item.data.activity === "trace" && content.trace) {
    return <TraceRunner backLink={backLink} chars={content.trace.chars} onFinish={handleFinish} />;
  }

  if (item.data.activity === "match" && content.match) {
    return <MatchRunner backLink={backLink} onFinish={handleFinish} pairs={content.match.pairs} />;
  }

  if (item.data.activity === "sentence" && content.sentence) {
    return (
      <SentenceRunner backLink={backLink} onFinish={handleFinish} sentences={[content.sentence]} />
    );
  }

  return <LessonShell>This lesson has no playable content.</LessonShell>;
}

function PathBackLink() {
  return (
    <Link className="inline-flex py-2 text-sm font-semibold text-mist hover:text-porcelain" to="/">
      ‹ Path
    </Link>
  );
}

function LessonShell({ children }: { children: ReactNode }) {
  return (
    <main className="min-h-screen bg-ink px-4 py-5 text-porcelain sm:px-6">
      <div className="mx-auto w-full max-w-[440px]">
        <PathBackLink />
        <p className="mt-8 text-sm text-mist">{children}</p>
      </div>
    </main>
  );
}
