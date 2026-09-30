import { expect, test } from "@playwright/test";

import { installMockApi } from "./mock-api";

test("viewer can inspect evidence but cannot mutate findings or projects", async ({ page }) => {
  await installMockApi(page, { viewer: true, seededProject: true });
  await page.goto("/login");
  await page.getByLabel("Email").fill("viewer@example.test");
  await page.getByLabel("Password").fill("Viewer-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "What is ready to merge?" })).toBeVisible();
  await page.goto("/analyses/analysis-1/findings");
  await expect(page.getByText("Shell execution accepts untrusted input")).toBeVisible();
  await page.getByRole("button", { name: /shell execution accepts untrusted input/i }).click();
  await expect(page.getByRole("combobox", { name: /review status/i })).toBeDisabled();
  await expect(page.getByText("Your viewer role is read-only.")).toBeVisible();
  await page.getByRole("link", { name: "Projects" }).click();
  await expect(page.getByText("Demo Service")).toBeVisible();
  await expect(page.getByRole("button", { name: "New project" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /project actions/i })).toHaveCount(0);
});
