import { expect, test } from "@playwright/test";

import { installMockApi } from "./mock-api";

test("demo user creates a project and completes an evidence-backed analysis", async ({ page }) => {
  await installMockApi(page);
  await page.goto("/login");
  await page.getByRole("button", { name: /enter the demo workspace/i }).click();
  await expect(page.getByRole("heading", { name: "What is ready to merge?" })).toBeVisible();
  await page.getByRole("link", { name: "Projects" }).click();
  await page.getByRole("button", { name: "New project" }).click();
  await page.getByLabel("Name").fill("Demo Service");
  await page.getByLabel("Description").fill("Acceptance scope for a small FastAPI service.");
  await page.getByRole("dialog").getByRole("button", { name: "Create project" }).click();
  await expect(page.getByRole("heading", { name: "Demo Service" })).toBeVisible();
  await page.locator("#main-content").getByRole("button", { name: "New analysis" }).click();
  await expect(page.getByText("Select the evidence source")).toBeVisible();
  await page.getByRole("button", { name: /continue/i }).click();
  await page.getByLabel(/requirement or user story/i).fill("Expose a safe health endpoint.");
  await page.getByRole("button", { name: /continue/i }).click();
  await page.getByRole("button", { name: /continue/i }).click();
  await page.getByRole("button", { name: /run analysis/i }).click();
  await expect(page.getByRole("heading", { name: "Evidence collection complete" })).toBeVisible();
  await page.getByRole("button", { name: /open results/i }).click();
  await expect(page.getByText("Review before acceptance")).toBeVisible();
  await page.getByRole("link", { name: "Findings", exact: true }).click();
  await expect(page.getByText("Shell execution accepts untrusted input")).toBeVisible();
  await page.getByRole("link", { name: "Impact graph" }).click();
  await expect(page.getByLabel("Code impact graph")).toBeVisible();
  await page.getByRole("link", { name: "Evidence", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Evidence manifest verified" })).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: /download zip/i }).click();
  expect((await download).suggestedFilename()).toContain("proofstack-evidence");
});
