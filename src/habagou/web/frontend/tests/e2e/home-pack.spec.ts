import { expect, test } from "@playwright/test";

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

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/packs", async (route) => {
    await route.fulfill({ json: [packSummary] });
  });
  await page.route("**/api/v1/packs/greetings", async (route) => {
    await route.fulfill({ json: packDetail });
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
    page.getByRole("button", { name: "Trace. Write each character stroke by stroke" }),
  ).toBeVisible();
});
