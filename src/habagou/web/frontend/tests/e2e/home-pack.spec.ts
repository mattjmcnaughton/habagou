import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { SCRIPTED_STROKE_COMPLETE_EVENT } from "../../src/components/trace-canvas";

const packsUnderTest = ["greetings", "numbers"] as const;

test.describe.configure({ mode: "serial" });

test.beforeEach(async ({ request }) => {
  await resetPacks(request);
});

test.afterEach(async ({ request }) => {
  await resetPacks(request);
});

test("[WF-02] navigates from home to pack detail", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Choose a pack" })).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Greetings pack, 5 characters, 3 sentences" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Greetings pack, 5 characters, 3 sentences" }).click();

  await expect(page).toHaveURL("/packs/greetings");
  await expect(page.getByRole("heading", { name: "Greetings" })).toBeVisible();
  await expect(page.getByTitle("nǐ · you")).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Trace. Write each character stroke by stroke" }),
  ).toBeVisible();
});

test("[WF-03] completes a traced pack and records progress", async ({ page }) => {
  await page.goto("/packs/numbers");

  await page.getByRole("link", { name: "Trace. Write each character stroke by stroke" }).click();
  await expect(page).toHaveURL("/packs/numbers/trace");

  for (const [index, hanzi] of ["一", "二", "三", "四", "五"].entries()) {
    await completeTraceCharacter(page, hanzi);
    await page.getByRole("button", { name: index === 4 ? "Finish" : "Next character" }).click();
  }

  await expect(page.getByRole("heading", { name: "Pack traced!" })).toBeVisible();
  await expect(page.getByText("Completion recorded.")).toBeVisible();

  await page.getByRole("link", { name: "Back to Numbers" }).click();
  await expect(
    page.getByRole("link", { name: "Trace, completed. Write each character stroke by stroke" }),
  ).toBeVisible();
});

test("[WF-04] completes a full match and records progress", async ({ page }) => {
  await page.goto("/packs/numbers/match?shuffleSeed=e2e");

  await expect(page.getByRole("heading", { name: "Match characters" })).toBeVisible();
  await expect(page.getByText("0 / 5")).toBeVisible();

  for (const pair of [
    ["一 character", "one, yī"],
    ["二 character", "two, èr"],
    ["三 character", "three, sān"],
    ["四 character", "four, sì"],
    ["五 character", "five, wǔ"],
  ] as const) {
    await page.getByRole("button", { name: pair[0] }).click();
    await page.getByRole("button", { name: pair[1] }).click();
  }

  await expect(page.getByRole("heading", { name: "All matched!" })).toBeVisible();
  await expect(page.getByText(/Finished in \d+s\./)).toBeVisible();
  await expect(page.getByText("Completion recorded.")).toBeVisible();

  await page.getByRole("link", { name: "Back to Numbers" }).click();
  await expect(
    page.getByRole("link", { name: "Match, completed. Pair characters with their meanings" }),
  ).toBeVisible();
});

test("[WF-05] traces a sentence with a sentence-only character", async ({ page }) => {
  const strokeRequests: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    const parts = url.pathname.split("/");
    if (parts[1] === "api" && parts[3] === "characters" && parts[5] === "strokes") {
      strokeRequests.push(decodeURIComponent(parts[4]));
    }
  });

  await page.goto("/packs/greetings/sentence");
  await expect(page.getByRole("heading", { name: "Hello" })).toBeVisible();

  await completeSentenceCharacter(page, "你");
  await page.getByRole("button", { name: "Next character" }).click();
  await completeSentenceCharacter(page, "好", "你好 done.");
  await page.getByRole("button", { name: "Next sentence" }).click();

  await expect(page.getByRole("heading", { name: "I am well" })).toBeVisible();
  await completeSentenceCharacter(page, "我");
  await page.getByRole("button", { name: "Next character" }).click();
  await completeSentenceCharacter(page, "很");
  await page.getByRole("button", { name: "Next character" }).click();
  await completeSentenceCharacter(page, "好", "我很好 done.");
  await page.getByRole("button", { name: "Next sentence" }).click();

  await completeSentenceCharacter(page, "谢");
  await page.getByRole("button", { name: "Next character" }).click();
  await completeSentenceCharacter(page, "谢");
  await page.getByRole("button", { name: "Next character" }).click();
  await completeSentenceCharacter(page, "你", "谢谢你 done.");
  await page.getByRole("button", { name: "Finish" }).click();

  await expect(page.getByRole("heading", { name: "Sentences complete!" })).toBeVisible();
  await expect(page.getByText("Completion recorded.")).toBeVisible();
  await expect.poll(() => strokeRequests).toContain("很");

  await page.getByRole("link", { name: "Back to Greetings" }).click();
  await expect(
    page.getByRole("link", { name: "Sentences, completed. Write full sentences from the pack" }),
  ).toBeVisible();
});

test("[WF-06] serves stroke data through the running app", async ({ request }) => {
  const response = await request.get("/api/v1/characters/你/strokes");

  expect(response.ok()).toBe(true);
  expect(response.headers()["cache-control"]).toContain("immutable");
  const body = (await response.json()) as { medians: unknown[]; strokes: unknown[] };
  expect(body.strokes.length).toBeGreaterThan(0);
  expect(body.medians.length).toBe(body.strokes.length);
});

test("[WF-07] shows recorded progress on the pack screen", async ({ page, request }) => {
  await recordCompletion(request, "numbers", "match");

  await page.goto("/packs/numbers");

  await expect(page.getByRole("heading", { name: "Numbers" })).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Match, completed. Pair characters with their meanings" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Trace. Write each character stroke by stroke" }),
  ).toBeVisible();
});

test("[WF-08] resets guest progress for a pack", async ({ page, request }) => {
  await recordCompletion(request, "numbers", "trace");
  await recordCompletion(request, "numbers", "match");

  await page.goto("/packs/numbers");
  await expect(
    page.getByRole("link", { name: "Trace, completed. Write each character stroke by stroke" }),
  ).toBeVisible();

  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toContain("Reset your progress for Numbers?");
    await dialog.accept();
  });
  await page.getByRole("button", { name: "Reset progress for this pack" }).click();

  await expect(page.getByText("Progress reset. 2 completions cleared.")).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Trace. Write each character stroke by stroke" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Match. Pair characters with their meanings" }),
  ).toBeVisible();
});

async function completeTraceCharacter(page: Page, hanzi: string) {
  const canvas = page.getByTestId("trace-canvas");
  await expect(canvas).toHaveAttribute("data-hanzi", hanzi);
  await canvas.dispatchEvent(SCRIPTED_STROKE_COMPLETE_EVENT);
  await expect(page.getByText(`Nice. That is ${hanzi}.`)).toBeVisible();
}

async function completeSentenceCharacter(page: Page, hanzi: string, doneText?: string) {
  const canvas = page.getByTestId("trace-canvas");
  await expect(canvas).toHaveAttribute("data-hanzi", hanzi);
  await canvas.dispatchEvent(SCRIPTED_STROKE_COMPLETE_EVENT);
  await expect(page.getByText(doneText ?? `Nice. That is ${hanzi}.`)).toBeVisible();
}

async function recordCompletion(
  request: APIRequestContext,
  packSlug: string,
  activity: "match" | "sentence" | "trace",
) {
  const response = await request.post("/api/v1/progress/completions", {
    data: {
      activity,
      duration_ms: 1000,
      pack_slug: packSlug,
    },
  });
  expect(response.status()).toBe(201);
}

async function resetPacks(request: APIRequestContext) {
  for (const slug of packsUnderTest) {
    const response = await request.delete(`/api/v1/progress/packs/${slug}`);
    expect(response.ok()).toBe(true);
  }
}
