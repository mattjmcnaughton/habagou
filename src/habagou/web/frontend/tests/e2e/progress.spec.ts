import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { SCRIPTED_STROKE_COMPLETE_EVENT } from "../../src/components/trace-canvas";
import { signIn } from "./auth-helpers";

const packsUnderTest = ["greetings", "numbers", "family", "food-drink"] as const;

test.describe.configure({ mode: "serial" });

test.beforeEach(async ({ page }) => {
  await signIn(page);
  await resetPacks(page.request);
});

test.afterEach(async ({ page }) => {
  await resetPacks(page.request);
});

test("[WF-11] progress dashboard reflects a completed activity in goal and heatmap", async ({
  page,
}) => {
  const today = localDateKey(new Date());

  await page.goto("/progress");

  await expect(page.getByText("0/3")).toBeVisible();
  await expect(page.locator("p").filter({ hasText: "0-day streak" })).toBeVisible();
  await expect(page.getByText("7-day streak")).toBeVisible();

  await page.goto("/packs/numbers/trace");
  for (const [index, hanzi] of ["一", "二", "三", "四", "五"].entries()) {
    await completeTraceCharacter(page, hanzi);
    await page.getByRole("button", { name: index === 4 ? "Finish" : "Next character" }).click();
  }
  await expect(page.getByRole("heading", { name: "Pack traced!" })).toBeVisible();

  await page.goto("/progress");

  await expect(page.getByText("1/3")).toBeVisible();
  await expect(page.locator(`[title="${today}"][data-level="1"]`).first()).toBeVisible();
});

test("[WF-11] heatmap expands to the month grid", async ({ page }) => {
  await page.goto("/progress");

  const activity = page.getByRole("button", { expanded: false });
  await expect(activity).toBeVisible();
  await activity.click();

  const expanded = page.getByRole("button", { expanded: true });
  await expect(page.getByText("This month")).toBeVisible();
  await expect(expanded.getByText("Less")).toBeVisible();
  await expect(expanded.getByText("More")).toBeVisible();

  await expanded.click();

  await expect(page.getByText("Tap to expand")).toBeVisible();
});

async function completeTraceCharacter(page: Page, hanzi: string) {
  const canvas = page.getByTestId("trace-canvas");
  await expect(canvas).toHaveAttribute("data-hanzi", hanzi);
  // The scripted-stroke listener is attached in the same effect that renders the
  // HanziWriter <svg>; wait for it so a freshly-mounted canvas doesn't drop the event.
  await expect(canvas.locator("svg")).toBeAttached();
  await canvas.dispatchEvent(SCRIPTED_STROKE_COMPLETE_EVENT);
  await expect(page.getByText(`Nice. That is ${hanzi}.`)).toBeVisible();
}

async function resetPacks(request: APIRequestContext) {
  for (const slug of packsUnderTest) {
    const response = await request.delete(`/api/v1/progress/packs/${slug}`);
    expect(response.ok()).toBe(true);
  }
}

function localDateKey(date: Date): string {
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("-");
}
