import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useEffect } from "react";
import type { PackDetail } from "../lib/api";
import { deletePack, getPack, resetPackProgress, setPackEnabled } from "../lib/api";
import { AUDIO_PRONUNCIATION_FLAG, useFeatureFlag } from "../lib/feature-flags";
import { useSpeak } from "../lib/speech";
import { prefetchPackStrokeData } from "../lib/strokes";

export const Route = createFileRoute("/packs/$packId")({
  component: PackScreen,
});

const activities = [
  {
    key: "trace",
    title: "Trace",
    subtitle: "Write each character stroke by stroke",
    icon: "✎",
    to: "/packs/$packId/trace",
  },
  {
    key: "match",
    title: "Match",
    subtitle: "Pair characters with their meanings",
    icon: "⌘",
    to: "/packs/$packId/match",
  },
  {
    key: "sentence",
    title: "Sentences",
    subtitle: "Write full sentences from the pack",
    icon: "☰",
    to: "/packs/$packId/sentence",
  },
] as const;

function PackScreen() {
  const { packId } = Route.useParams();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { speak, supported: speechSupported } = useSpeak();
  const audioEnabled = useFeatureFlag(AUDIO_PRONUNCIATION_FLAG) && speechSupported;
  const pack = useQuery({ queryKey: ["pack", packId], queryFn: () => getPack(packId) });
  useEffect(() => {
    if (pack.data) {
      void prefetchPackStrokeData(queryClient, pack.data);
    }
  }, [pack.data, queryClient]);

  const reset = useMutation({
    mutationFn: () => resetPackProgress(packId),
    onSuccess: (result) => {
      queryClient.setQueryData<PackDetail>(["pack", packId], (current) =>
        current ? { ...current, progress: result.progress } : current,
      );
      queryClient.invalidateQueries({ queryKey: ["packs"] });
    },
  });

  // Library enablement for global (unowned) packs: enabling puts the pack on
  // the bench; disabling takes it off but keeps the user's progress. Owned
  // packs are always enabled and keep the Delete flow instead.
  const setEnabled = useMutation({
    mutationFn: (enabled: boolean) => setPackEnabled(packId, enabled),
    onSuccess: (_result, enabled) => {
      queryClient.invalidateQueries({ queryKey: ["packs"] });
      queryClient.invalidateQueries({ queryKey: ["library"] });
      queryClient.invalidateQueries({ queryKey: ["pack", packId] });
      if (!enabled) {
        void navigate({ to: "/packs" });
      }
    },
  });

  const remove = useMutation({
    mutationFn: () => deletePack(packId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["packs"] });
      queryClient.removeQueries({ queryKey: ["pack", packId] });
      void navigate({ to: "/" });
    },
  });

  function resetProgress() {
    if (!window.confirm(`Reset your progress for ${pack.data?.title ?? "this pack"}?`)) {
      return;
    }
    reset.mutate();
  }

  function deleteThisPack() {
    const title = pack.data?.title ?? "this pack";
    if (
      !window.confirm(
        `Delete "${title}"? This permanently removes the pack and your progress for it.`,
      )
    ) {
      return;
    }
    remove.mutate();
  }

  return (
    <main className="min-h-screen bg-ink px-4 py-5 text-porcelain sm:px-6">
      <div className="mx-auto w-full max-w-[440px]">
        <Link
          className="inline-flex py-2 text-sm font-semibold text-mist hover:text-porcelain"
          to="/"
        >
          ‹ All packs
        </Link>

        {pack.isPending ? <p className="mt-8 text-sm text-mist">Loading pack...</p> : null}
        {pack.isError ? <p className="mt-8 text-sm text-clay">Pack could not be loaded.</p> : null}

        {pack.data ? (
          <>
            <section className="mt-4 rounded-lg border border-white/10 bg-panel shadow-panel">
              <div className="flex items-center gap-5 border-b border-white/10 p-5">
                <div
                  className="flex h-24 w-24 shrink-0 items-center justify-center rounded-md font-hanzi text-6xl"
                  style={{
                    backgroundColor: `${pack.data.color}22`,
                    color: pack.data.color,
                  }}
                >
                  {pack.data.glyph}
                </div>
                <div>
                  <h1 className="text-2xl font-bold leading-tight">{pack.data.title}</h1>
                  <p className="mt-2 text-sm leading-5 text-mist">
                    {pack.data.char_count} characters · {pack.data.sentence_count} sentences
                  </p>
                </div>
              </div>

              {!pack.data.owned && !pack.data.enabled ? (
                <div className="border-b border-white/10 p-4">
                  <button
                    aria-label={`Enable ${pack.data.title}`}
                    className="w-full rounded-md bg-jade px-4 py-3 text-sm font-bold text-ink transition-colors hover:bg-jade-bright disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={setEnabled.isPending}
                    onClick={() => setEnabled.mutate(true)}
                    type="button"
                  >
                    {setEnabled.isPending ? "Adding..." : "Add to my packs"}
                  </button>
                  {setEnabled.isError ? (
                    <p className="mt-3 text-sm text-clay" role="alert">
                      The pack could not be added.
                    </p>
                  ) : null}
                </div>
              ) : null}

              <div className="flex flex-wrap gap-2 border-b border-white/10 p-4">
                {pack.data.characters.map((character) => {
                  const chipClassName =
                    "rounded-md border border-white/10 bg-white/[0.03] px-3 py-2 font-hanzi text-xl";
                  const title = `${character.pinyin} · ${character.meaning}`;
                  if (!audioEnabled) {
                    return (
                      <span className={chipClassName} key={character.hanzi} title={title}>
                        {character.hanzi}
                      </span>
                    );
                  }
                  return (
                    <button
                      aria-label={`Hear ${character.hanzi} (${character.pinyin})`}
                      className={`${chipClassName} transition-colors hover:border-jade hover:text-jade`}
                      key={character.hanzi}
                      onClick={() => speak(character.hanzi)}
                      title={title}
                      type="button"
                    >
                      {character.hanzi}
                    </button>
                  );
                })}
              </div>

              <div className="divide-y divide-white/10">
                {activities.map((activity) => {
                  const progress = pack.data.progress[activity.key];
                  const content = (
                    <>
                      <span
                        aria-hidden="true"
                        className="flex h-11 w-11 items-center justify-center rounded-md text-xl"
                        style={{ color: pack.data.color }}
                      >
                        {activity.icon}
                      </span>
                      <span>
                        <span className="flex flex-wrap items-center gap-2 text-base font-semibold">
                          {activity.title}
                          {progress.completed ? (
                            <span className="rounded-full border border-jade/30 bg-jade/10 px-2 py-0.5 text-xs font-normal text-jade">
                              ✓ completed
                            </span>
                          ) : null}
                        </span>
                        <span className="mt-1 block text-sm leading-5 text-mist">
                          {activity.subtitle}
                        </span>
                      </span>
                      <span className="text-2xl text-mist" aria-hidden="true">
                        ›
                      </span>
                    </>
                  );
                  return (
                    <Link
                      aria-label={`${activity.title}${progress.completed ? ", completed" : ""}. ${activity.subtitle}`}
                      className="grid w-full grid-cols-[2.75rem_1fr_auto] items-center gap-4 p-4 text-left transition-colors hover:bg-white/[0.035]"
                      key={activity.key}
                      params={{ packId }}
                      to={activity.to}
                    >
                      {content}
                    </Link>
                  );
                })}
              </div>
            </section>

            <div className="mt-5 rounded-lg border border-white/10 bg-panel/60 p-4">
              <button
                className="w-full rounded-md border border-clay/40 px-4 py-3 text-sm font-semibold text-clay transition-colors hover:bg-clay/10 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={reset.isPending}
                onClick={resetProgress}
                type="button"
              >
                {reset.isPending ? "Resetting..." : "Reset progress for this pack"}
              </button>
              {reset.isSuccess ? (
                <p className="mt-3 text-sm text-mist">
                  Progress reset. {reset.data.deleted_count} completion
                  {reset.data.deleted_count === 1 ? "" : "s"} cleared.
                </p>
              ) : null}
              {reset.isError ? (
                <div className="mt-3" role="alert">
                  <p className="text-sm text-clay">Progress could not be reset.</p>
                  <button
                    className="mt-3 rounded-md border border-clay/40 px-3 py-2 text-sm font-semibold text-porcelain transition-colors hover:bg-clay/10 disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={reset.isPending}
                    onClick={() => reset.mutate()}
                    type="button"
                  >
                    {reset.isPending ? "Retrying..." : "Retry reset"}
                  </button>
                </div>
              ) : null}

              {!pack.data.owned && pack.data.enabled ? (
                <>
                  <button
                    aria-label={`Disable ${pack.data.title}`}
                    className="mt-3 w-full rounded-md border border-white/10 px-4 py-3 text-sm font-semibold text-mist transition-colors hover:bg-white/[0.05] disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={setEnabled.isPending}
                    onClick={() => setEnabled.mutate(false)}
                    type="button"
                  >
                    {setEnabled.isPending ? "Removing..." : "Remove from my packs"}
                  </button>
                  <p className="mt-2 text-sm text-mist">Your progress is kept.</p>
                  {setEnabled.isError ? (
                    <p className="mt-3 text-sm text-clay" role="alert">
                      The pack could not be removed.
                    </p>
                  ) : null}
                </>
              ) : null}

              {pack.data.owned ? (
                <>
                  <button
                    className="mt-3 w-full rounded-md border border-clay/40 px-4 py-3 text-sm font-semibold text-clay transition-colors hover:bg-clay/10 disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={remove.isPending}
                    onClick={deleteThisPack}
                    type="button"
                  >
                    {remove.isPending ? "Deleting..." : "Delete this pack"}
                  </button>
                  {remove.isError ? (
                    <div className="mt-3" role="alert">
                      <p className="text-sm text-clay">Pack could not be deleted.</p>
                      <button
                        className="mt-3 rounded-md border border-clay/40 px-3 py-2 text-sm font-semibold text-porcelain transition-colors hover:bg-clay/10 disabled:cursor-not-allowed disabled:opacity-50"
                        disabled={remove.isPending}
                        onClick={() => remove.mutate()}
                        type="button"
                      >
                        {remove.isPending ? "Retrying..." : "Retry delete"}
                      </button>
                    </div>
                  ) : null}
                </>
              ) : null}
            </div>
          </>
        ) : null}
      </div>
    </main>
  );
}
