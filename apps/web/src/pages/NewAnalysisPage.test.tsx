import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { api } from "../api/client";
import type { AnalysisRun, Project } from "../api/types";
import { renderPage } from "../test/utils";
import { NewAnalysisPage } from "./NewAnalysisPage";

const project: Project = {
  id: "project-1",
  name: "Demo Service",
  slug: "demo-service",
  description: "",
  default_branch: "main",
  repository_provider: "local",
  repository_url: null,
  created_at: "2025-01-01T00:00:00Z",
};

const analysis: AnalysisRun = {
  id: "analysis-1",
  project_id: project.id,
  source_type: "demo",
  status: "queued",
  verdict: "unknown",
  risk_score: 0,
  progress: 0,
};

const prepare = () => {
  vi.spyOn(api.projects, "list").mockResolvedValue({
    items: [project],
    total: 1,
    page: 1,
    page_size: 100,
  });
  vi.spyOn(api.policies, "list").mockResolvedValue({
    items: [{ name: "default" }],
    total: 1,
    page: 1,
    page_size: 1,
  });
};

const moveToReview = async () => {
  await screen.findByText("Select the evidence source");
  await userEvent.selectOptions(screen.getByLabelText("Project"), project.id);
  await userEvent.click(screen.getByRole("button", { name: /continue/i }));
  await userEvent.type(
    screen.getByLabelText(/requirement or user story/i),
    "Add a safe health endpoint.",
  );
  await userEvent.type(
    screen.getByLabelText(/acceptance criteria/i),
    "Authorization is validated.",
  );
  await userEvent.click(screen.getByRole("button", { name: /continue/i }));
  await userEvent.click(screen.getByRole("button", { name: /continue/i }));
};

describe("NewAnalysisPage", () => {
  it("completes all four steps and starts a real demo analysis", async () => {
    prepare();
    const startDemo = vi.spyOn(api.analyses, "startDemo").mockResolvedValue(analysis);
    renderPage(
      <Routes>
        <Route path="/analyses/new" element={<NewAnalysisPage />} />
        <Route path="/analyses/:analysisId/progress" element={<div>Live pipeline</div>} />
      </Routes>,
      ["/analyses/new"],
    );
    await moveToReview();
    expect(screen.getByText("Review the evidence plan")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: /run analysis/i }));
    await waitFor(() =>
      expect(startDemo).toHaveBeenCalledWith(
        project.id,
        expect.objectContaining({ requirements: "Add a safe health endpoint.", policy: "default" }),
      ),
    );
    expect(await screen.findByText("Live pipeline")).toBeVisible();
  });

  it("builds the hardened upload multipart contract", async () => {
    prepare();
    const startUpload = vi
      .spyOn(api.analyses, "startUpload")
      .mockResolvedValue({ ...analysis, source_type: "upload" });
    renderPage(<NewAnalysisPage />, ["/analyses/new"]);
    await screen.findByText("Select the evidence source");
    await userEvent.selectOptions(screen.getByLabelText("Project"), project.id);
    await userEvent.click(screen.getByRole("radio", { name: /zip \+ diff/i }));
    const archive = new File(["archive"], "source.zip", { type: "application/zip" });
    const patch = new File(["diff --git"], "change.diff", { type: "text/plain" });
    await userEvent.upload(screen.getByLabelText(/choose source zip/i), archive);
    await userEvent.upload(screen.getByLabelText(/choose diff or patch/i), patch);
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    await userEvent.type(screen.getByLabelText(/requirement or user story/i), "Upload requirement");
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    await userEvent.click(screen.getByRole("button", { name: /run analysis/i }));
    await waitFor(() => expect(startUpload).toHaveBeenCalled());
    const form = startUpload.mock.calls[0]?.[1];
    expect(form?.get("source")).toBe(archive);
    expect(form?.get("diff")).toBe(patch);
    expect(form?.get("policy_name")).toBe("default");
    expect(form?.has("install_dependencies")).toBe(false);
  });
});
