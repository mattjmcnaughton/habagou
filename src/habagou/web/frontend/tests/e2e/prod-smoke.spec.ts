import { expect, test } from "@playwright/test";

test.skip(!process.env.BASE_URL, "production smoke requires BASE_URL");

test("[WF-10] @smoke verifies health and readiness probes", async ({ request }) => {
  const health = await request.get("/healthz");
  expect(health.ok(), await responseText(health)).toBe(true);
  await expect(health.json()).resolves.toEqual({ status: "ok" });

  const ready = await request.get("/readyz");
  expect(ready.ok(), await responseText(ready)).toBe(true);
  await expect(ready.json()).resolves.toEqual({ status: "ready" });
});

test("[WF-02] @smoke browses the published pack library", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Choose a pack" })).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Greetings pack, 5 characters, 3 sentences" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Greetings pack, 5 characters, 3 sentences" }).click();

  await expect(page).toHaveURL("/packs/greetings");
  await expect(page.getByRole("heading", { name: "Greetings" })).toBeVisible();
  await expect(page.getByTitle("nǐ · you")).toBeVisible();
});

test("[WF-06] @smoke fetches immutable stroke data", async ({ request }) => {
  const response = await request.get("/api/v1/characters/你/strokes");

  expect(response.ok(), await responseText(response)).toBe(true);
  expect(response.headers()["cache-control"]).toContain("immutable");
  const body = (await response.json()) as { medians: unknown[]; strokes: unknown[] };
  expect(body.strokes.length).toBeGreaterThan(0);
  expect(body.medians.length).toBe(body.strokes.length);
});

async function responseText(response: { text(): Promise<string> }) {
  try {
    return await response.text();
  } catch {
    return "<response body unavailable>";
  }
}
