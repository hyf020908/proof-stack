import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { api } from "../api/client";
import type { Project, Role } from "../api/types";
import { useAuthStore } from "../auth/store";
import { renderPage } from "../test/utils";
import { ProjectsPage } from "./ProjectsPage";

const project: Project = {
  id: "project-1",
  name: "Payments API",
  slug: "payments-api",
  description: "Evidence scope for the payment service.",
  default_branch: "main",
  repository_provider: "github",
  repository_url: "https://github.com/example/payments",
  created_at: "2025-01-01T00:00:00Z",
  analyses_count: 3,
  latest_verdict: "warn",
};

const setRole = (role: Role) =>
  useAuthStore.setState({
    accessToken: "token",
    refreshToken: "refresh",
    hydrated: true,
    user: {
      id: "user-1",
      organization_id: "org-1",
      email: `${role}@example.test`,
      display_name: role,
      role,
      is_active: true,
    },
  });

describe("ProjectsPage", () => {
  it("renders API projects and their repository context", async () => {
    setRole("owner");
    vi.spyOn(api.projects, "list").mockResolvedValue({
      items: [project],
      total: 1,
      page: 1,
      page_size: 100,
    });
    renderPage(<ProjectsPage />);
    expect(await screen.findByText("Payments API")).toBeVisible();
    expect(screen.getByText("Evidence scope for the payment service.")).toBeVisible();
    expect(screen.getByText("warn")).toBeVisible();
  });

  it("creates a project from validated form data", async () => {
    setRole("maintainer");
    vi.spyOn(api.projects, "list").mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 100,
    });
    const create = vi.spyOn(api.projects, "create").mockResolvedValue(project);
    renderPage(<ProjectsPage />);
    await screen.findByText("Create an evidence scope");
    await userEvent.click(screen.getByRole("button", { name: "New project" }));
    await userEvent.type(screen.getByLabelText("Name"), "Payments API");
    await userEvent.type(
      screen.getByLabelText(/description/i),
      "Evidence scope for the payment service.",
    );
    await userEvent.click(screen.getAllByRole("button", { name: "Create project" }).at(-1)!);
    await waitFor(() =>
      expect(create).toHaveBeenCalledWith(
        expect.objectContaining({ name: "Payments API", default_branch: "main" }),
      ),
    );
  });

  it("enforces viewer read-only permissions", async () => {
    setRole("viewer");
    vi.spyOn(api.projects, "list").mockResolvedValue({
      items: [project],
      total: 1,
      page: 1,
      page_size: 100,
    });
    renderPage(<ProjectsPage />);
    expect(await screen.findByText("Payments API")).toBeVisible();
    expect(screen.queryByRole("button", { name: "New project" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /project actions/i })).not.toBeInTheDocument();
  });

  it("provides an actionable API error state", async () => {
    setRole("owner");
    vi.spyOn(api.projects, "list").mockRejectedValue(new Error("Repository service unavailable"));
    renderPage(<ProjectsPage />);
    expect(await screen.findByText("Repository service unavailable")).toBeVisible();
    expect(screen.getByRole("button", { name: "Try again" })).toBeEnabled();
  });
});
