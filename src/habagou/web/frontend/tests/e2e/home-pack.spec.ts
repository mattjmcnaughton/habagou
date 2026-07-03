import { expect, test } from "@playwright/test";
import { SCRIPTED_STROKE_COMPLETE_EVENT } from "../../src/components/trace-events";

const blankProgress = {
  trace: { completed: false, completion_count: 0, best_duration_ms: null },
  match: { completed: false, completion_count: 0, best_duration_ms: null },
  sentence: { completed: false, completion_count: 0, best_duration_ms: null },
};

const packSummary = {
  id: "11111111-1111-4111-8111-111111111111",
  slug: "greetings",
  title: "Greetings",
  glyph: "你",
  color: "#c4633f",
  char_count: 5,
  sentence_count: 3,
  progress: blankProgress,
};

const numbersSummary = {
  id: "22222222-2222-4222-8222-222222222222",
  slug: "numbers",
  title: "Numbers",
  glyph: "一",
  color: "#3f8a86",
  char_count: 1,
  sentence_count: 1,
  progress: blankProgress,
};

const packDetail = {
  ...packSummary,
  characters: [
    { hanzi: "你", pinyin: "nǐ", meaning: "you" },
    { hanzi: "好", pinyin: "hǎo", meaning: "good" },
    { hanzi: "我", pinyin: "wǒ", meaning: "I, me" },
    { hanzi: "他", pinyin: "tā", meaning: "he, him" },
    { hanzi: "谢", pinyin: "xiè", meaning: "thanks" },
  ],
  sentences: [
    { hanzi: "你好", pinyin: "nǐ hǎo", translation: "Hello" },
    { hanzi: "我很好", pinyin: "wǒ hěn hǎo", translation: "I am well" },
    { hanzi: "谢谢你", pinyin: "xièxie nǐ", translation: "Thank you" },
  ],
};

const numbersDetail = {
  ...numbersSummary,
  characters: [{ hanzi: "一", pinyin: "yī", meaning: "one" }],
  sentences: [{ hanzi: "一", pinyin: "yī", translation: "One" }],
};

test.beforeEach(async ({ page }) => {
  let sentenceCompleted = false;
  let traceCompleted = false;
  let matchCompleted = false;
  const greetingsProgress = () => ({
    ...blankProgress,
    sentence: sentenceCompleted
      ? { completed: true, completion_count: 1, best_duration_ms: 1000 }
      : blankProgress.sentence,
  });
  const numbersProgress = () => ({
    ...blankProgress,
    trace: traceCompleted
      ? { completed: true, completion_count: 1, best_duration_ms: 1000 }
      : blankProgress.trace,
    match: matchCompleted
      ? { completed: true, completion_count: 1, best_duration_ms: 1000 }
      : blankProgress.match,
  });
  await page.route("**/api/v1/packs", async (route) => {
    await route.fulfill({
      json: [
        { ...packSummary, progress: greetingsProgress() },
        {
          ...numbersSummary,
          progress: numbersProgress(),
        },
      ],
    });
  });
  await page.route("**/api/v1/packs/greetings", async (route) => {
    await route.fulfill({ json: { ...packDetail, progress: greetingsProgress() } });
  });
  await page.route("**/api/v1/packs/numbers", async (route) => {
    await route.fulfill({
      json: {
        ...numbersDetail,
        progress: numbersProgress(),
      },
    });
  });
  await page.route("**/api/v1/characters/*/strokes", async (route) => {
    await route.fulfill({
      json: {
        strokes: ["M 128 512 L 896 512"],
        medians: [
          [
            [128, 512],
            [896, 512],
          ],
        ],
      },
    });
  });
  await page.route("**/api/v1/progress/completions", async (route) => {
    const body = await route.request().postDataJSON();
    if (body.pack_slug === "numbers" && body.activity === "trace") {
      traceCompleted = true;
    }
    if (body.pack_slug === "numbers" && body.activity === "match") {
      matchCompleted = true;
    }
    if (body.pack_slug === "greetings" && body.activity === "sentence") {
      sentenceCompleted = true;
    }
    await route.fulfill({
      json: {
        ...body,
        progress: body.pack_slug === "greetings" ? greetingsProgress() : numbersProgress(),
      },
    });
  });
});

test("[WF-02] navigates from home to pack detail", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Choose a pack" })).toBeVisible();
  await page.getByRole("link", { name: "Greetings pack, 5 characters, 3 sentences" }).click();

  await expect(page).toHaveURL("/packs/greetings");
  await expect(page.getByRole("heading", { name: "Greetings" })).toBeVisible();
  await expect(page.getByTitle("nǐ · you")).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Trace. Write each character stroke by stroke" }),
  ).toBeVisible();
});

test("[WF-03] completes a one-stroke trace and records progress", async ({ page }) => {
  await page.goto("/packs/numbers");

  await page.getByRole("link", { name: "Trace. Write each character stroke by stroke" }).click();
  await expect(page).toHaveURL("/packs/numbers/trace");
  await expect(page.getByText("Stroke 1 of 1")).toBeVisible();

  const canvas = page.getByTestId("trace-canvas");
  const box = await canvas.boundingBox();
  if (!box) {
    throw new Error("Trace canvas did not render a box");
  }
  await page.mouse.move(box.x + box.width * 0.22, box.y + box.height * 0.5);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.78, box.y + box.height * 0.5, { steps: 12 });
  await page.mouse.up();
  await canvas.dispatchEvent(SCRIPTED_STROKE_COMPLETE_EVENT);

  await expect(page.getByText("Nice. That is 一.")).toBeVisible();
  await page.getByRole("button", { name: "Finish" }).click();
  await expect(page.getByRole("heading", { name: "Pack traced!" })).toBeVisible();
  await expect(page.getByText("Completion recorded.")).toBeVisible();

  await page.getByRole("link", { name: "Back to Numbers" }).click();
  await expect(
    page.getByRole("link", { name: "Trace, completed. Write each character stroke by stroke" }),
  ).toBeVisible();
});

test("[WF-04] completes a full match and records progress", async ({ page }) => {
  await page.goto("/packs/numbers");

  await page.getByRole("link", { name: "Match. Pair characters with their meanings" }).click();
  await expect(page).toHaveURL("/packs/numbers/match");
  await expect(page.getByRole("heading", { name: "Match characters" })).toBeVisible();
  await expect(page.getByText("0 / 1")).toBeVisible();

  await page.getByRole("button", { name: "一 character" }).click();
  await page.getByRole("button", { name: "one, yī" }).click();

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

  await page.goto("/packs/greetings");

  await page.getByRole("link", { name: "Sentences. Write full sentences from the pack" }).click();
  await expect(page).toHaveURL("/packs/greetings/sentence");
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

async function completeSentenceCharacter(
  page: import("@playwright/test").Page,
  hanzi: string,
  doneText?: string,
) {
  const canvas = page.getByTestId("trace-canvas");
  await expect(canvas).toHaveAttribute("data-hanzi", hanzi);
  await expect(page.getByText("Stroke 1 of 1")).toBeVisible();
  await canvas.dispatchEvent(SCRIPTED_STROKE_COMPLETE_EVENT);
  await expect(page.getByText(doneText ?? `Nice. That is ${hanzi}.`)).toBeVisible();
}
