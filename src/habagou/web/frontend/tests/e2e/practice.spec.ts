import { expect, test } from "@playwright/test";
import { signIn } from "./auth-helpers";

test.skip(!!process.env.BASE_URL, "WF-16 requires the stub e2e backend (scripts/e2e_backend.py)");

// Conversational practice, end to end (WF-16 / ADR 0011). The backend under
// test is scripts/e2e_backend.py: the real API, but a deterministic,
// network-free practice model. That stub always opens with 你好 / 你想吃什么 and,
// on a follow-up turn, replies 好的 / 你要喝什么 with an English aside — see its
// determinism guard in tests/unit/test_e2e_backend.py.

test.beforeEach(async ({ page }) => {
  await signIn(page);
});

test("[WF-16] opens a conversation from a starter topic and taps to reveal English", async ({
  page,
}) => {
  // The Practice tab is a first-class top-level surface.
  await page.getByRole("link", { name: "Practice" }).click();
  await expect(page).toHaveURL("/practice");
  await expect(page.getByRole("heading", { name: /Practice/ })).toBeVisible();

  // The dev Keycloak user is not an admin, so the model-picker chrome (ADM-04)
  // must be absent: the status response returns no model list for non-admins.
  await expect(page.getByText("Model", { exact: true })).toHaveCount(0);

  // Start from a starter chip; the tutor opens the conversation.
  await page.getByRole("button", { name: "Ordering food at a restaurant" }).click();
  await expect(page.getByText("你好", { exact: true })).toBeVisible();
  await expect(page.getByText("nǐ hǎo", { exact: true })).toBeVisible();
  await expect(page.getByText("你想吃什么")).toBeVisible();

  // English is hidden until the segment is tapped, and only for that segment.
  await expect(page.getByText("Hello!")).toBeHidden();
  await page.getByRole("button", { name: /你好/ }).click();
  await expect(page.getByText("Hello!")).toBeVisible();
  await expect(page.getByText("What do you want to eat?")).toBeHidden();

  // Tapping again hides it.
  await page.getByRole("button", { name: /你好/ }).click();
  await expect(page.getByText("Hello!")).toBeHidden();
});

test("[WF-16] follows up in mixed language, sees the English aside, and resets", async ({
  page,
}) => {
  await page.goto("/practice");
  await page.getByRole("button", { name: "Ordering food at a restaurant" }).click();
  await expect(page.getByText("你好", { exact: true })).toBeVisible();

  // Reply (the learner may write English, Chinese, or a mix).
  await page.getByRole("textbox").fill("what does 喝 mean?");
  await page.getByRole("button", { name: "Send" }).click();

  // The follow-up turn renders new segments plus the break-glass aside.
  await expect(page.getByText("你要喝什么")).toBeVisible();
  await expect(page.getByRole("note", { name: "English aside" })).toContainText("to drink");
  // The earlier tutor turn stays in the transcript.
  await expect(page.getByText("你好", { exact: true })).toBeVisible();

  // "New" discards the ephemeral conversation and returns to the topic picker.
  await page.getByRole("button", { name: "New", exact: true }).click();
  await expect(page.getByText("What would you like to talk about?")).toBeVisible();
  await expect(page.getByText("你要喝什么")).toBeHidden();
});
