import { expect, test } from "@playwright/test";

import { installMockApi } from "./mock-api";

test("maintainer submits ZIP and diff evidence through the four-step wizard", async ({ page }) => {
  await installMockApi(page, { seededProject: true });
  await page.goto("/login");
  await page.getByLabel("Email").fill("owner@example.test");
  await page.getByLabel("Password").fill("Strong-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("banner").getByRole("button", { name: "New analysis" }).click();
  await page.getByLabel("Project").selectOption("project-1");
  await page.getByRole("radio", { name: /zip \+ diff/i }).click();
  await page.getByLabel(/choose source zip/i).setInputFiles({
    name: "source.zip",
    mimeType: "application/zip",
    buffer: Buffer.from("safe zip fixture"),
  });
  await page.getByLabel(/choose diff or patch/i).setInputFiles({
    name: "change.diff",
    mimeType: "text/plain",
    buffer: Buffer.from("diff --git a/app.py b/app.py"),
  });
  await page.getByRole("button", { name: /continue/i }).click();
  await page
    .getByLabel(/requirement or user story/i)
    .fill("Preserve the public API response schema.");
  await page
    .getByLabel(/acceptance criteria/i)
    .fill("Authorization is covered by integration tests.");
  await page.getByRole("button", { name: /continue/i }).click();
  await page.getByLabel("Policy").selectOption("default");
  await page.getByRole("button", { name: /continue/i }).click();
  await expect(page.getByText("source.zip")).toBeVisible();
  await page.getByRole("button", { name: /run analysis/i }).click();
  await expect(page.getByRole("heading", { name: "Evidence collection complete" })).toBeVisible();
});
