import { expect, type Page } from "@playwright/test";

export async function signIn(page: Page) {
  await page.goto("/");
  if (
    await page
      .getByTestId("path-shell")
      .isVisible()
      .catch(() => false)
  ) {
    return;
  }

  await expect(page.getByRole("heading", { name: "Sign in to keep your streak" })).toBeVisible();
  await page.getByRole("link", { name: /Continue with/ }).click();
  await page.getByLabel(/username/i).fill("dev");
  await page.locator("#password").fill("dev");
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page.getByTestId("path-shell")).toBeVisible();
}
