import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { api } from "../api/client";
import type { AnalysisRun, Finding, PolicyDecision } from "../api/types";
import { useAuthStore } from "../auth/store";
import { renderPage } from "../test/utils";
import { AnalysisPage } from "./AnalysisPage";
import { FindingsTab } from "./analysis/FindingsTab";
import { OverviewTab } from "./analysis/OverviewTab";
import { PoliciesTab } from "./analysis/PoliciesTab";

const analysis: AnalysisRun = {
  id: "analysis-1",
  project_id: "project-1",
  source_type: "demo",
  source_reference: "Demo signature change",
  status: "completed",
  verdict: "warn",
  risk_score: 67,
  progress: 100,
  started_at: "2025-01-01T00:00:00Z",
  metrics: { changed_files: 7, additions: 88, deletions: 21, requirement_coverage: 0.62 },
};

const finding: Finding = {
  id: "finding-1",
  category: "security",
  severity: "high",
  title: "Shell execution accepts untrusted input",
  description: "A shell-enabled subprocess was introduced.",
  file_path: "app/service.py",
  start_line: 44,
  rule_id: "python-shell-true",
  remediation: "Pass a validated argument array without a shell.",
  evidence: { call: "subprocess.run", secret: "[REDACTED]" },
  status: "open",
};

const decision: PolicyDecision = {
  id: "decision-1",
  policy_name: "default",
  rule_id: "requirement-coverage",
  outcome: "warn",
  explanation: "Requirement evidence coverage is below 70 percent.",
  observed_value: 0.62,
  expected_value: 0.7,
  operator: "gte",
  evidence_references: ["requirements.json"],
};

const mockAnalysis = () => vi.spyOn(api.analyses, "get").mockResolvedValue(analysis);

describe("Analysis evidence views", () => {
  it("renders the explainable verdict and risk summary", async () => {
    mockAnalysis();
    vi.spyOn(api.analyses, "findings").mockResolvedValue({
      items: [finding],
      total: 1,
      page: 1,
      page_size: 100,
    });
    vi.spyOn(api.analyses, "files").mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 100,
    });
    vi.spyOn(api.analyses, "requirements").mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 100,
    });
    vi.spyOn(api.analyses, "tests").mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 100,
    });
    vi.spyOn(api.analyses, "policies").mockResolvedValue({
      items: [decision],
      total: 1,
      page: 1,
      page_size: 100,
    });
    renderPage(
      <Routes>
        <Route path="/analyses/:analysisId" element={<AnalysisPage />}>
          <Route index element={<OverviewTab />} />
        </Route>
      </Routes>,
      ["/analyses/analysis-1"],
    );
    expect(await screen.findByText("Review before acceptance")).toBeVisible();
    expect(screen.getByText("67")).toBeVisible();
    expect(await screen.findByText("Shell execution accepts untrusted input")).toBeVisible();
  });

  it("filters findings and keeps viewer status controls read-only", async () => {
    mockAnalysis();
    useAuthStore.setState({
      accessToken: "token",
      refreshToken: "refresh",
      user: {
        id: "viewer",
        organization_id: "org-1",
        email: "viewer@example.test",
        display_name: "View Only",
        role: "viewer",
        is_active: true,
      },
    });
    vi.spyOn(api.analyses, "findings").mockResolvedValue({
      items: [
        finding,
        {
          ...finding,
          id: "finding-2",
          title: "Missing integration test",
          category: "test",
          severity: "medium",
        },
      ],
      total: 2,
      page: 1,
      page_size: 100,
    });
    renderPage(
      <Routes>
        <Route path="/analyses/:analysisId" element={<AnalysisPage />}>
          <Route path="findings" element={<FindingsTab />} />
        </Route>
      </Routes>,
      ["/analyses/analysis-1/findings"],
    );
    expect(await screen.findByText("Shell execution accepts untrusted input")).toBeVisible();
    await userEvent.selectOptions(screen.getByLabelText("Category"), "security");
    expect(screen.queryByText("Missing integration test")).not.toBeInTheDocument();
    const findingButton = screen.getByRole("button", {
      name: /shell execution accepts untrusted input/i,
    });
    await userEvent.click(findingButton);
    await waitFor(() => expect(findingButton).toHaveAttribute("aria-expanded", "true"));
    expect(await screen.findByRole("combobox", { name: /review status/i })).toBeDisabled();
    expect(screen.getByText("Your viewer role is read-only.")).toBeVisible();
  });

  it("shows observed and expected values for policy decisions", async () => {
    mockAnalysis();
    vi.spyOn(api.analyses, "policies").mockResolvedValue({
      items: [decision],
      total: 1,
      page: 1,
      page_size: 100,
    });
    renderPage(
      <Routes>
        <Route path="/analyses/:analysisId" element={<AnalysisPage />}>
          <Route path="policies" element={<PoliciesTab />} />
        </Route>
      </Routes>,
      ["/analyses/analysis-1/policies"],
    );
    expect(await screen.findByText("Requirement Coverage")).toBeVisible();
    expect(screen.getByText("0.62")).toBeVisible();
    expect(screen.getByText("0.7")).toBeVisible();
    expect(screen.getByText("requirements.json")).toBeVisible();
  });
});
