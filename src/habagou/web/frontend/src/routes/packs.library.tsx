import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import type { Library, LibraryPack } from "../lib/api";
import { getGenerationStatus, getLibrary, setPackEnabled } from "../lib/api";

// The pack library: the curated catalog of global packs, grouped by category.
// Users enable packs here to place them on the bench (/packs/); disabling keeps
// their progress. AI creation lives at the bottom as the fallback entry point.
export const Route = createFileRoute("/packs/library")({
  component: LibraryScreen,
});

function LibraryScreen() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const library = useQuery({ queryKey: ["library"], queryFn: getLibrary });
  // A status-probe failure must never break the library, so AI entry points only
  // appear once the server reports generation is configured (issue #102 / S6-A).
  const generation = useQuery({ queryKey: ["generation-status"], queryFn: getGenerationStatus });

  const toggle = useMutation({
    mutationFn: (vars: { packId: string; enabled: boolean }) =>
      setPackEnabled(vars.packId, vars.enabled),
    // Optimistic: flip the pack in the ["library"] cache immediately, roll back
    // on error, and reconcile with the server on settle.
    onMutate: async (vars) => {
      await queryClient.cancelQueries({ queryKey: ["library"] });
      const previous = queryClient.getQueryData<Library>(["library"]);
      queryClient.setQueryData<Library>(["library"], (current) =>
        current
          ? {
              categories: current.categories.map((category) => ({
                ...category,
                packs: category.packs.map((pack) =>
                  pack.id === vars.packId ? { ...pack, enabled: vars.enabled } : pack,
                ),
              })),
            }
          : current,
      );
      return { previous };
    },
    onError: (_error, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData<Library>(["library"], context.previous);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["packs"] });
      queryClient.invalidateQueries({ queryKey: ["library"] });
    },
  });

  const query = search.trim().toLowerCase();
  const matches = (pack: LibraryPack) =>
    query.length === 0 ||
    pack.title.toLowerCase().includes(query) ||
    (pack.description ?? "").toLowerCase().includes(query);
  const categories = (library.data?.categories ?? [])
    .map((category) => ({ ...category, packs: category.packs.filter(matches) }))
    .filter((category) => category.packs.length > 0);
  const noMatches = library.isSuccess && query.length > 0 && categories.length === 0;
  const generationEnabled = generation.data?.enabled === true;

  return (
    <main className="min-h-screen bg-ink text-porcelain">
      <div className="mx-auto w-full max-w-[440px]">
        <header className="grid grid-cols-[auto_1fr_auto] items-center gap-3 border-b border-white/10 px-4 py-3">
          <Link
            aria-label="Back to packs"
            className="text-sm font-semibold text-mist transition-colors hover:text-porcelain"
            to="/packs"
          >
            ‹ Packs
          </Link>
          <h1 className="text-center text-base font-bold">
            Pack library <span className="font-hanzi text-jade">书库</span>
          </h1>
          <span aria-hidden="true" className="w-12" />
        </header>

        <div className="px-4 py-5">
          <input
            aria-label="Search the library"
            className="w-full rounded-xl border border-white/10 bg-panel px-4 py-3 text-porcelain placeholder:text-mist focus:border-jade/40 focus:outline-none"
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search packs"
            type="search"
            value={search}
          />

          {library.isPending ? (
            <p className="mt-5 text-sm text-mist">Loading the library...</p>
          ) : null}
          {library.isError ? (
            <p className="mt-5 text-sm text-clay">The library could not be loaded.</p>
          ) : null}

          {categories.map((category) => (
            <section className="mt-6" key={category.slug}>
              <h2 className="text-xs font-semibold uppercase tracking-[0.16em] text-mist">
                {category.title}
              </h2>
              <div className="mt-3 divide-y divide-white/10 rounded-lg border border-white/10 bg-panel shadow-panel">
                {category.packs.map((pack) => (
                  <LibraryPackRow
                    key={pack.id}
                    onToggle={() => toggle.mutate({ packId: pack.id, enabled: !pack.enabled })}
                    pack={pack}
                  />
                ))}
              </div>
            </section>
          ))}

          {noMatches ? (
            <div className="mt-8 text-center">
              <p className="text-sm text-mist">No packs match your search.</p>
              {generationEnabled ? (
                <Link
                  className="mt-3 inline-block text-sm font-semibold text-jade transition-colors hover:text-jade-bright"
                  to="/packs/generate"
                >
                  Can't find it? Create your own pack with AI
                </Link>
              ) : null}
            </div>
          ) : null}

          {generationEnabled ? <CreatePackCard /> : null}

          <footer className="mt-8 pb-3 text-center font-hanzi text-sm text-mist/80">
            一笔一画
          </footer>
        </div>
      </div>
    </main>
  );
}

function LibraryPackRow({ onToggle, pack }: { onToggle: () => void; pack: LibraryPack }) {
  return (
    <div className="flex items-center gap-4 p-4 transition-colors hover:bg-white/[0.035]">
      <Link
        aria-label={`${pack.title} pack, ${pack.char_count} characters, ${pack.sentence_count} sentences`}
        className="flex min-w-0 flex-1 items-center gap-4 text-left"
        params={{ packId: pack.id }}
        to="/packs/$packId"
      >
        <span
          aria-hidden="true"
          className="flex h-14 w-14 shrink-0 items-center justify-center rounded-md font-hanzi text-3xl"
          style={{ backgroundColor: `${pack.color}22`, color: pack.color }}
        >
          {pack.glyph}
        </span>
        <span className="min-w-0">
          <span className="block text-base font-semibold leading-6">{pack.title}</span>
          {pack.description ? (
            <span className="block text-sm leading-5 text-mist">{pack.description}</span>
          ) : null}
          <span className="mt-0.5 block text-sm leading-5 text-mist">
            {pack.char_count} characters · {pack.sentence_count} sentences
          </span>
        </span>
      </Link>
      <button
        aria-label={pack.enabled ? `Disable ${pack.title}` : `Enable ${pack.title}`}
        className={
          pack.enabled
            ? "shrink-0 rounded-md border border-white/10 px-3 py-2 text-sm font-semibold text-mist transition-colors hover:bg-white/[0.05]"
            : "shrink-0 rounded-md bg-jade px-3 py-2 text-sm font-bold text-ink transition-colors hover:bg-jade-bright"
        }
        onClick={onToggle}
        type="button"
      >
        {pack.enabled ? "Enabled ✓" : "Enable"}
      </button>
    </div>
  );
}

// The AI fallback entry point, demoted from the bench into the library: when
// the curated catalog doesn't cover a topic, draft a pack instead.
function CreatePackCard() {
  return (
    <Link
      aria-label="Create a pack — describe a topic and we'll draft characters and sentences"
      className="mt-8 grid grid-cols-[3.5rem_1fr_auto] items-center gap-4 rounded-lg border border-dashed border-jade/40 bg-jade/[0.04] p-4 text-left transition-colors hover:border-jade/60 hover:bg-jade/[0.08]"
      to="/packs/generate"
    >
      <span
        aria-hidden="true"
        className="flex h-14 w-14 items-center justify-center rounded-md bg-jade/10 font-hanzi text-3xl text-jade"
      >
        造
      </span>
      <span className="min-w-0">
        <span className="flex flex-wrap items-center gap-2">
          <span className="text-base font-semibold leading-6">Create a pack</span>
          <span className="rounded-full border border-jade/30 bg-jade/10 px-2 py-0.5 text-xs font-semibold text-jade">
            AI · BETA
          </span>
        </span>
        <span className="mt-0.5 block text-sm leading-5 text-mist">
          Describe a topic — we'll draft characters &amp; sentences.
        </span>
      </span>
      <span className="text-2xl text-jade/70" aria-hidden="true">
        ›
      </span>
    </Link>
  );
}
