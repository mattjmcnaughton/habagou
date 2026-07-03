import { createFileRoute } from "@tanstack/react-router";
import type { PackSummary } from "../lib/api";

export const Route = createFileRoute("/")({
  component: Index,
});

const packs: Pick<
  PackSummary,
  "slug" | "title" | "glyph" | "color" | "char_count" | "sentence_count"
>[] = [
  {
    slug: "greetings",
    title: "Greetings",
    glyph: "你",
    color: "#c4633f",
    char_count: 5,
    sentence_count: 3,
  },
  {
    slug: "numbers",
    title: "Numbers",
    glyph: "三",
    color: "#3f8a86",
    char_count: 5,
    sentence_count: 2,
  },
  {
    slug: "family",
    title: "Family",
    glyph: "妈",
    color: "#5b5fa8",
    char_count: 5,
    sentence_count: 2,
  },
  {
    slug: "food-drink",
    title: "Food & drink",
    glyph: "茶",
    color: "#b5852e",
    char_count: 5,
    sentence_count: 2,
  },
];

function Index() {
  return (
    <main className="min-h-screen bg-ink px-4 py-5 text-porcelain sm:px-6">
      <div className="mx-auto flex min-h-[calc(100vh-2.5rem)] w-full max-w-[440px] flex-col">
        <header className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-baseline gap-2">
              <h1 className="text-[1.45rem] font-bold leading-none tracking-normal">Habagou</h1>
              <span className="font-hanzi text-lg text-jade">哈巴狗</span>
            </div>
            <p className="mt-3 max-w-[17rem] text-base leading-6 text-mist">
              Learn to write Chinese characters, stroke by stroke.
            </p>
          </div>
          <div className="flex h-8 shrink-0 items-center gap-2 rounded-full border border-white/10 bg-panel px-3 text-sm text-mist">
            <span className="h-2 w-2 rounded-full bg-jade" />
            Guest
          </div>
        </header>

        <section className="mt-8 rounded-lg border border-white/10 bg-panel shadow-panel">
          <div className="flex items-center gap-5 border-b border-white/10 p-5">
            <div className="flex h-24 w-24 shrink-0 items-center justify-center rounded-md bg-jade/10 font-hanzi text-6xl text-jade">
              你
            </div>
            <div>
              <p className="text-sm uppercase tracking-[0.16em] text-mist">Writing bench</p>
              <h2 className="mt-2 text-2xl font-bold leading-tight">Choose a pack</h2>
            </div>
          </div>

          <div className="divide-y divide-white/10">
            {packs.map((pack) => (
              <button
                className="grid w-full grid-cols-[3.5rem_1fr_auto] items-center gap-4 p-4 text-left transition-colors hover:bg-white/[0.035]"
                key={pack.slug}
                type="button"
              >
                <span
                  className="flex h-14 w-14 items-center justify-center rounded-md font-hanzi text-3xl"
                  style={{ backgroundColor: `${pack.color}22`, color: pack.color }}
                >
                  {pack.glyph}
                </span>
                <span className="min-w-0">
                  <span className="block text-base font-semibold leading-6">{pack.title}</span>
                  <span className="block text-sm leading-5 text-mist">
                    {pack.char_count} characters · {pack.sentence_count} sentences
                  </span>
                  <span className="mt-2 flex flex-wrap gap-1.5">
                    <span className="rounded-full border border-white/10 px-2 py-0.5 text-xs text-mist">
                      trace
                    </span>
                    <span className="rounded-full border border-white/10 px-2 py-0.5 text-xs text-mist">
                      match
                    </span>
                    <span className="rounded-full border border-white/10 px-2 py-0.5 text-xs text-mist">
                      sentence
                    </span>
                  </span>
                </span>
                <span className="text-2xl text-mist" aria-hidden="true">
                  ›
                </span>
              </button>
            ))}
          </div>
        </section>

        <footer className="mt-auto pt-8 text-center font-hanzi text-sm text-mist/80">
          一笔一画
        </footer>
      </div>
    </main>
  );
}
