import { expect, test } from "@playwright/test";
import { signIn } from "./auth-helpers";

test.skip(!!process.env.BASE_URL, "WF-15 requires the stub e2e backend (scripts/e2e_backend.py)");

// Agent pack generation, end to end (issue #102 / WF-15). The backend under
// test is scripts/e2e_backend.py: the real API and seeded corpus, but a
// deterministic, network-free generation model. That stub always drafts
// "Ordering Food" (4 characters + one sentence) on the first turn and, on a
// refinement turn, grows it to 6 characters — see its determinism guard in
// tests/unit/test_e2e_backend.py.
test.describe.configure({ mode: "serial" });

// The two Playwright projects (desktop + mobile) run these against ONE backend
// process and ONE Keycloak user, so a saved pack persists across projects. The
// library assertion tolerates a sibling project's duplicate with .first(); the
// rate cap is disabled in the stub backend so repeated drafts never 429.
const LIBRARY_LINK = /Ordering Food pack, 6 characters, 1 sentences/;

test.beforeEach(async ({ page }) => {
  await signIn(page);
});

test("[WF-15] drafts a corpus-grounded preview from a topic", async ({ page }) => {
  await page.goto("/packs");

  // The "Create a pack" entry point only appears when generation is enabled,
  // which the stub backend reports true.
  await page.getByRole("link", { name: /Create a pack/ }).click();
  await expect(page).toHaveURL("/packs/generate");
  await expect(page.getByRole("heading", { name: /Create a pack/ })).toBeVisible();

  await page.getByRole("textbox").fill("Ordering at a restaurant");
  await page.getByRole("button", { name: "Send" }).click();

  // A draft preview renders: title, characters with pinyin + meaning, and a
  // coverage note in the canonical "Found N of M — ..." shape.
  await expect(page.getByRole("heading", { level: 2, name: "Ordering Food" })).toBeVisible();
  await expect(page.getByText("4 characters · 1 sentences · draft")).toBeVisible();
  // exact avoids also matching the sentence pinyin ("nǐ hǎo · Hello").
  await expect(page.getByText("nǐ", { exact: true })).toBeVisible();
  await expect(page.getByText("you", { exact: true })).toBeVisible();
  await expect(page.getByRole("note", { name: "Coverage note" })).toContainText("Found 4 of 4");
});

test("[WF-15] refines, saves, and traces a generated pack", async ({ page }) => {
  await page.goto("/packs/generate");

  // First draft.
  await page.getByRole("textbox").fill("Ordering at a restaurant");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByRole("heading", { level: 2, name: "Ordering Food" })).toBeVisible();
  await expect(page.getByText("4 characters · 1 sentences · draft")).toBeVisible();

  // Refine — the stub grows the pack to 6 characters on a second turn.
  await page.getByRole("textbox").fill("make it harder");
  await page.getByRole("button", { name: "Send" }).click();

  // The updated preview supersedes the first draft: the earlier draft collapses
  // to a compact chip, and the new one shows a "Draft 2" badge and 6 characters.
  await expect(page.getByText("Draft 1 · Ordering Food · 4 characters")).toBeVisible();
  await expect(page.getByText("6 characters · 1 sentences · draft")).toBeVisible();
  await expect(page.getByText("Draft 2", { exact: true })).toBeVisible();

  // Save — lands on the new pack's detail page.
  await page.getByRole("button", { name: "Save pack" }).click();
  await expect(page).toHaveURL(/\/packs\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("heading", { level: 1, name: "Ordering Food" })).toBeVisible();

  // It appears in the Packs library (tolerating a sibling project's duplicate).
  await page.goto("/packs");
  await expect(page.getByRole("heading", { name: "Choose a pack" })).toBeVisible();
  const libraryLink = page.getByRole("link", { name: LIBRARY_LINK }).first();
  await expect(libraryLink).toBeVisible();

  // Open it and start the trace flow: the canvas loads the first character.
  await libraryLink.click();
  await expect(page.getByRole("heading", { level: 1, name: "Ordering Food" })).toBeVisible();
  await page.getByRole("link", { name: "Trace. Write each character stroke by stroke" }).click();
  await expect(page).toHaveURL(/\/packs\/[0-9a-f-]{36}\/trace$/);

  const canvas = page.getByTestId("trace-canvas");
  await expect(canvas).toHaveAttribute("data-hanzi", "你");
  await expect(canvas.locator("svg")).toBeAttached();
});
