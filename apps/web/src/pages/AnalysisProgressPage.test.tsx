import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { api } from "../api/client";
import type { AnalysisRun } from "../api/types";
import { renderPage } from "../test/utils";
import { AnalysisProgressPage } from "./AnalysisProgressPage";

const analysis: AnalysisRun = {
  id: "analysis-1",
  project_id: "project-1",
  source_type: "demo",
  status: "analyzing",
  verdict: "unknown",
  risk_score: 0,
  progress: 42,
  current_stage: "ANALYZE_IMPACT",
};

describe("AnalysisProgressPage", () => {
  it("polls and displays stage and structured event evidence", async () => {
    vi.spyOn(api.analyses, "get").mockResolvedValue(analysis);
    vi.spyOn(api.analyses, "progress").mockResolvedValue({
      status: "analyzing",
      progress: 42,
      current_stage: "ANALYZE_IMPACT",
      stages: [
        { name: "PREPARE_SOURCE", status: "completed", duration_ms: 120 },
        { name: "ANALYZE_IMPACT", status: "running" },
      ],
    });
    vi.spyOn(api.analyses, "events").mockResolvedValue({
      items: [
        {
          id: "event-1",
          stage: "ANALYZE_IMPACT",
          level: "info",
          message: "Mapped 14 affected symbols",
          created_at: "2025-01-01T00:00:00Z",
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });
    renderPage(
      <Routes>
        <Route path="/analyses/:analysisId/progress" element={<AnalysisProgressPage />} />
      </Routes>,
      ["/analyses/analysis-1/progress"],
    );
    expect(await screen.findByText("Collecting acceptance evidence")).toBeVisible();
    expect(screen.getAllByText("Analyze Impact").length).toBeGreaterThan(0);
    expect(await screen.findByText("Mapped 14 affected symbols")).toBeVisible();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "42");
  });

  it("cancels an active run with an auditable API action", async () => {
    vi.spyOn(api.analyses, "get").mockResolvedValue(analysis);
    vi.spyOn(api.analyses, "progress").mockResolvedValue({
      status: "analyzing",
      progress: 42,
      current_stage: "ANALYZE_IMPACT",
    });
    vi.spyOn(api.analyses, "events").mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
    });
    const cancel = vi
      .spyOn(api.analyses, "cancel")
      .mockResolvedValue({ ...analysis, status: "cancelled" });
    renderPage(
      <Routes>
        <Route path="/analyses/:analysisId/progress" element={<AnalysisProgressPage />} />
      </Routes>,
      ["/analyses/analysis-1/progress"],
    );
    await userEvent.click(await screen.findByRole("button", { name: /cancel run/i }));
    await waitFor(() => expect(cancel).toHaveBeenCalledWith("analysis-1"));
  });
});
