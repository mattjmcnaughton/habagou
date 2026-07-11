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

test("[WF-AUTH-SIGN-IN] @smoke renders the login screen", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Sign in to keep your streak" })).toBeVisible();
  await expect(page.getByRole("link", { name: /Continue with/ })).toBeVisible();
});

test("[WF-AUTH-GATE] @smoke gates data APIs", async ({ request }) => {
  const response = await request.get("/api/v1/characters/你/strokes");

  expect(response.status(), await responseText(response)).toBe(401);
  await expect(response.json()).resolves.toMatchObject({
    error: { code: "unauthenticated" },
  });
});

test("[WF-AUTH-SIGN-IN] @smoke reports an anonymous session", async ({ request }) => {
  const response = await request.get("/api/v1/auth/session");

  expect(response.ok(), await responseText(response)).toBe(true);
  await expect(response.json()).resolves.toMatchObject({ authenticated: false });
});

async function responseText(response: { text(): Promise<string> }) {
  try {
    return await response.text();
  } catch {
    return "<response body unavailable>";
  }
}
