import { expect, test } from "@playwright/test";
import { signIn } from "./auth-helpers";
import { fetchLibraryPacks, packIdByTitle, resetLibraryEnablement } from "./pack-helpers";

// The pack library (curated catalog), end to end: a fresh user's bench holds
// only the starter packs; enabling a pack in the library puts it on the bench,
// disabling takes it off while keeping progress. Both Playwright projects share
// one backend and one Keycloak user, so every spec restores the fresh-user
// enablement defaults around itself.
test.describe.configure({ mode: "serial" });

test.beforeEach(async ({ page }) => {
  await signIn(page);
  await resetLibraryEnablement(page.request);
});

test.afterEach(async ({ page }) => {
  await resetLibraryEnablement(page.request);
});

test("[WF-LIB] enables a library pack onto the bench and disables it again", async ({ page }) => {
  // Fresh-user default: exactly the four starter packs are enabled.
  const starters = (await fetchLibraryPacks(page.request)).filter((pack) => pack.starter);
  expect(starters).toHaveLength(4);

  await page.goto("/packs");
  await expect(page.getByRole("heading", { name: "Choose a pack" })).toBeVisible();
  for (const pack of starters) {
    await expect(
      page.getByRole("link", { name: new RegExp(`^${pack.title} pack, `) }),
    ).toBeVisible();
  }
  // AI creation is no longer offered on the bench.
  await expect(page.getByRole("link", { name: /Create a pack/ })).toHaveCount(0);

  // Open the library via the bench card.
  await page.getByRole("link", { name: /Browse the library/ }).click();
  await expect(page).toHaveURL("/packs/library");
  await expect(page.getByRole("heading", { name: /Pack library/ })).toBeVisible();

  // Enable a non-starter pack; the toggle quiets down once it is on the bench.
  await page.getByRole("button", { name: "Enable Fruit" }).click();
  await expect(page.getByRole("button", { name: "Disable Fruit" })).toBeVisible();

  // Back on the bench, the pack now appears.
  await page.getByRole("link", { name: "Back to packs" }).click();
  await expect(page.getByRole("heading", { name: "Choose a pack" })).toBeVisible();
  await expect(page.getByRole("link", { name: /^Fruit pack, / })).toBeVisible();

  // Disable it from the library again; the bench no longer shows it.
  await page.getByRole("link", { name: /Browse the library/ }).click();
  await page.getByRole("button", { name: "Disable Fruit" }).click();
  await expect(page.getByRole("button", { name: "Enable Fruit" })).toBeVisible();
  await page.getByRole("link", { name: "Back to packs" }).click();
  await expect(page.getByRole("heading", { name: "Choose a pack" })).toBeVisible();
  await expect(page.getByRole("link", { name: /^Fruit pack, / })).toHaveCount(0);
});

test("[WF-LIB] removes a starter pack from its detail page and restores it from the library", async ({
  page,
}) => {
  const greetingsId = await packIdByTitle(page.request, "Greetings");
  await page.goto(`/packs/${greetingsId}`);
  await expect(page.getByRole("heading", { name: "Greetings" })).toBeVisible();

  // An enabled global pack offers the low-emphasis remove action; disabling
  // keeps the user's progress.
  await expect(page.getByText("Your progress is kept.")).toBeVisible();
  await page.getByRole("button", { name: "Disable Greetings" }).click();

  // Removing lands back on the bench, which has shrunk by one pack.
  await expect(page).toHaveURL("/packs");
  await expect(page.getByRole("heading", { name: "Choose a pack" })).toBeVisible();
  await expect(page.getByRole("link", { name: /^Greetings pack, / })).toHaveCount(0);

  // Re-enabling from the library restores it.
  await page.getByRole("link", { name: /Browse the library/ }).click();
  await page.getByRole("button", { name: "Enable Greetings" }).click();
  await expect(page.getByRole("button", { name: "Disable Greetings" })).toBeVisible();
  await page.getByRole("link", { name: "Back to packs" }).click();
  await expect(page.getByRole("link", { name: /^Greetings pack, / })).toBeVisible();
});
