import { expect, test } from "@playwright/test";
import { signIn } from "./auth-helpers";
import { packIdByTitle } from "./pack-helpers";

test.skip(!!process.env.BASE_URL, "requires the stub e2e backend (scripts/e2e_backend.py)");

// User-scoped pack deletion, end to end. Owned packs are created through the
// deterministic stub generation flow (scripts/e2e_backend.py always drafts
// "Ordering Food" on the first turn), then deleted from their detail screen.
// Curated packs are undeletable, so their detail screen offers no delete button.
test.describe.configure({ mode: "serial" });

test.beforeEach(async ({ page }) => {
  await signIn(page);
});

test("[WF-DELETE] deletes an owned pack and drops it from the library", async ({ page }) => {
  // Create an owned pack via the stubbed generation chat flow.
  await page.goto("/packs/generate");
  await page.getByRole("textbox").fill("Ordering at a restaurant");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByRole("heading", { level: 2, name: "Ordering Food" })).toBeVisible();

  // Saving lands on the new pack's detail page.
  await page.getByRole("button", { name: "Save pack" }).click();
  await expect(page).toHaveURL(/\/packs\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("heading", { level: 1, name: "Ordering Food" })).toBeVisible();
  const packId = new URL(page.url()).pathname.split("/").at(-1);

  // The owned pack exposes a delete affordance.
  const deleteButton = page.getByRole("button", { name: "Delete this pack" });
  await expect(deleteButton).toBeVisible();

  // Accept the confirmation dialog, which spells out that the removal is
  // permanent and also clears the user's progress.
  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toContain('Delete "Ordering Food"?');
    expect(dialog.message()).toContain("permanently removes the pack and your progress");
    await dialog.accept();
  });
  await deleteButton.click();

  // Deleting redirects home (the Path shell), off the now-gone detail route.
  await expect(page).toHaveURL("/");

  // The pack is gone from the library. Check by id, not title: the sibling
  // Playwright project's generate-pack spec leaves its own saved "Ordering
  // Food" pack behind on the shared backend, so a title match would collide.
  await page.goto("/packs");
  await expect(page.getByRole("heading", { name: "Choose a pack" })).toBeVisible();
  await expect(page.locator(`a[href="/packs/${packId}"]`)).toHaveCount(0);
});

test("[WF-DELETE] shows no delete button for a curated pack", async ({ page }) => {
  const greetingsId = await packIdByTitle(page.request, "Greetings");
  await page.goto(`/packs/${greetingsId}`);

  await expect(page.getByRole("heading", { name: "Greetings" })).toBeVisible();
  // Curated packs are not owned by the user, so no delete affordance renders.
  await expect(page.getByRole("button", { name: "Reset progress for this pack" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Delete this pack" })).toHaveCount(0);
});
