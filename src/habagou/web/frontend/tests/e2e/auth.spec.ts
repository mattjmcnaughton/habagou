import { expect, test } from "@playwright/test";
import { signIn } from "./auth-helpers";

test("[WF-AUTH-SIGN-IN] signs in through Keycloak", async ({ page }) => {
  await signIn(page);

  await expect(page).toHaveURL("/");
  await expect(page.getByTestId("path-shell")).toBeVisible();
  await expect(page.getByText("Dev User")).toBeVisible();
});

test("[WF-AUTH-SIGN-OUT] signs out and returns to login", async ({ page }) => {
  await signIn(page);

  await page.getByRole("button", { name: "Sign out" }).click();

  await expect(page.getByRole("heading", { name: "Sign in to keep your streak" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Sign in to keep your streak" })).toBeVisible();
});
