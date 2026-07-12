import { expect, test, type APIRequestContext, type Locator, type Page } from "@playwright/test";
import { SCRIPTED_STROKE_COMPLETE_EVENT } from "../../src/components/trace-canvas";
import type { PathItem, PathResponse } from "../../src/lib/api";
import { signIn } from "./auth-helpers";

// End-to-end coverage for the Learning Path (INT-1 / issue #77). These specs run
// against the live dev backend and a shared Postgres that accumulates path
// completions across runs, so every assertion checks presence/deltas — never an
// absolute count — and the current node is revealed through the real infinite
// scroll rather than assumed to sit on the first page.

test.describe.configure({ mode: "serial" });

test.beforeEach(async ({ page }) => {
  await signIn(page);
});

test("[WF-12] opens on the Path with a goal ring and a single current node", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("path-shell")).toBeVisible();

  // Hero goal ring (completed/target label) and the streak/due chips.
  await expect(page.getByTestId("path-goal-ring-label")).toBeVisible();
  await expect(page.getByTestId("path-goal-ring-label")).toHaveText(/^\d+\/\d+$/);
  await expect(page.getByText(/Due ·/)).toBeVisible();

  await expect(page.getByTestId("path-timeline")).toBeVisible();

  const current = await revealCurrentNode(page);
  await expect(current).toHaveCount(1);
  await expect(current.getByRole("link", { name: /Start lesson/ })).toBeVisible();
});

test("[WF-13] completes the current path lesson and advances the path", async ({ page }) => {
  const item = await fetchCurrentItem(page.request);

  await page.goto("/");
  const current = await revealCurrentNode(page);
  await current.getByRole("link", { name: /Start lesson/ }).click();

  // The lesson runner is full-screen: the persistent tab bar is gone.
  await expect(page).toHaveURL(new RegExp(`/lesson/${item.id}$`));
  await expect(page.locator('nav[aria-label="Primary"]')).toHaveCount(0);

  await completeActivity(page, item);

  // Done screen records the completion for a signed-in learner.
  await expect(page.getByRole("heading", { name: "Lesson complete!" })).toBeVisible();
  await expect(page.getByText("Completion recorded")).toBeVisible();

  await page.getByRole("link", { name: "Back to Path" }).click();
  await expect(page.getByTestId("path-shell")).toBeVisible();

  // The completed item is now done and a different item is current.
  const after = await fetchPathItemsUntil(page.request, (i) => i.id === item.id);
  const completed = after.find((i) => i.id === item.id);
  expect(completed?.state).toBe("done");
  const nextCurrent = await fetchCurrentItem(page.request);
  expect(nextCurrent.id).not.toBe(item.id);

  // UI reflects it: a done node exists and a fresh current node has a Start button.
  const revealed = await revealCurrentNode(page);
  await expect(revealed.getByRole("link", { name: /Start lesson/ })).toBeVisible();
  await expect(page.locator('[data-testid="path-node"][data-state="done"]').first()).toBeVisible();
});

test("[WF-13] leaves the affected pack's activity badges untouched", async ({ page }) => {
  const packs = await fetchPacks(page.request);
  const before = await readPackBadges(page, packs);

  // Complete one path lesson (the source='path' event must not touch pack badges).
  const item = await fetchCurrentItem(page.request);
  await page.goto("/");
  const current = await revealCurrentNode(page);
  await current.getByRole("link", { name: /Start lesson/ }).click();
  await completeActivity(page, item);
  await expect(page.getByText("Completion recorded")).toBeVisible();

  const after = await readPackBadges(page, packs);
  expect(after).toEqual(before);
});

test("[WF-14] shows the progress stats row with numeric tiles", async ({ page }) => {
  await page.goto("/progress");

  const row = page.getByTestId("progress-stats-row");
  await expect(row).toBeVisible();

  await expect(row.getByText("Characters")).toBeVisible();
  await expect(row.getByText("Packs")).toBeVisible();
  // Characters tile is a plain integer; Packs tile is "completed/total".
  await expect(row.getByText(/^\d+$/)).toBeVisible();
  await expect(row.getByText(/^\d+\/\d+$/)).toBeVisible();
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// Scroll the infinite-scroll sentinel into view until the single current node is
// loaded. The shared DB may carry many done-today items ahead of the current
// item, pushing it onto a later page, so we page in until it appears.
async function revealCurrentNode(page: Page): Promise<Locator> {
  const current = page.locator('[data-testid="path-node"][data-state="current"]');
  await expect(page.getByTestId("path-timeline")).toBeVisible();
  for (let i = 0; i < 25 && (await current.count()) === 0; i++) {
    const sentinel = page.getByTestId("path-load-more");
    if ((await sentinel.count()) === 0) {
      break;
    }
    await sentinel.scrollIntoViewIfNeeded();
    await page.waitForTimeout(400);
  }
  await expect(current).toHaveCount(1);
  return current;
}

async function completeActivity(page: Page, item: PathItem): Promise<void> {
  if (item.activity === "trace" && item.content.trace) {
    const chars = item.content.trace.chars;
    for (const [index, char] of chars.entries()) {
      await traceCharacter(page, char.hanzi);
      await page
        .getByRole("button", { name: index === chars.length - 1 ? "Finish" : "Next character" })
        .click();
    }
    return;
  }

  if (item.activity === "match" && item.content.match) {
    for (const pair of item.content.match.pairs) {
      await page.getByRole("button", { name: `${pair.hanzi} character`, exact: true }).click();
      await page
        .getByRole("button", { name: `${pair.meaning}, ${pair.pinyin}`, exact: true })
        .click();
    }
    return;
  }

  if (item.activity === "sentence" && item.content.sentence) {
    const sentence = item.content.sentence;
    const chars = Array.from(sentence.hanzi);
    for (const [index, char] of chars.entries()) {
      const last = index === chars.length - 1;
      await traceCharacter(page, char, last ? `${sentence.hanzi} done.` : undefined);
      await page.getByRole("button", { name: last ? "Finish" : "Next character" }).click();
    }
    return;
  }

  throw new Error(`path item ${item.id} has no playable ${item.activity} content`);
}

async function traceCharacter(page: Page, hanzi: string, doneText?: string): Promise<void> {
  const canvas = page.getByTestId("trace-canvas");
  await expect(canvas).toHaveAttribute("data-hanzi", hanzi);
  // The scripted-stroke listener is attached in the same effect that renders the
  // HanziWriter <svg>; wait for it so a freshly-mounted canvas doesn't drop the event.
  await expect(canvas.locator("svg")).toBeAttached();
  await canvas.dispatchEvent(SCRIPTED_STROKE_COMPLETE_EVENT);
  await expect(page.getByText(doneText ?? `Nice. That is ${hanzi}.`)).toBeVisible();
}

async function fetchCurrentItem(request: APIRequestContext): Promise<PathItem> {
  const items = await fetchPathItemsUntil(request, (item) => item.state === "current");
  const current = items.find((item) => item.state === "current");
  if (!current) {
    throw new Error("no current path item found");
  }
  return current;
}

// Page through /api/v1/path accumulating items until `predicate` matches one (or
// the path is exhausted). Returns every item seen so far.
async function fetchPathItemsUntil(
  request: APIRequestContext,
  predicate: (item: PathItem) => boolean,
): Promise<PathItem[]> {
  const seen: PathItem[] = [];
  let cursor: number | undefined = 0;
  for (let i = 0; i < 50; i++) {
    const query = cursor === undefined ? "" : `?cursor=${cursor}&limit=50`;
    const response = await request.get(`/api/v1/path${query}`);
    expect(response.ok(), await response.text()).toBeTruthy();
    const body = (await response.json()) as PathResponse;
    seen.push(...body.items);
    if (body.items.some(predicate) || body.next_cursor == null) {
      break;
    }
    cursor = body.next_cursor;
  }
  return seen;
}

type PackRef = { slug: string; title: string };

async function fetchPacks(request: APIRequestContext): Promise<PackRef[]> {
  const response = await request.get("/api/v1/packs");
  expect(response.ok(), await response.text()).toBeTruthy();
  const packs = (await response.json()) as PackRef[];
  return packs.map((pack) => ({ slug: pack.slug, title: pack.title }));
}

// Snapshot each pack's per-activity badge text (e.g. "✓ trace" vs "trace") from
// the /packs library, keyed by slug, so before/after can be compared exactly.
async function readPackBadges(page: Page, packs: PackRef[]): Promise<Record<string, string>> {
  await page.goto("/packs");
  await expect(page.getByRole("heading", { name: "Choose a pack" })).toBeVisible();

  const snapshot: Record<string, string> = {};
  for (const pack of packs) {
    const link = page.getByRole("link", { name: new RegExp(`^${escapeRegExp(pack.title)} pack,`) });
    const badges: string[] = [];
    for (const label of ["trace", "match", "sentence"] as const) {
      const badge = link.getByText(new RegExp(`(^|\\s)${label}$`)).first();
      badges.push(((await badge.textContent()) ?? "").trim());
    }
    snapshot[pack.slug] = badges.join("|");
  }
  return snapshot;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
