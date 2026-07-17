import type { Page, Route } from "@playwright/test";

const owner = {
  id: "user-owner",
  organization_id: "org-1",
  email: "owner@example.test",
  display_name: "Ada Owner",
  role: "owner",
  is_active: true,
};
const viewer = {
  ...owner,
  id: "user-viewer",
  email: "viewer@example.test",
  display_name: "Vera Viewer",
  role: "viewer",
};
const analysis = {
  id: "analysis-1",
  project_id: "project-1",
  source_type: "demo",
  source_reference: "Demo signature change",
  status: "completed",
  verdict: "warn",
  risk_score: 67,
  progress: 100,
  current_stage: "FINALIZE",
  started_at: "2025-01-01T00:00:00Z",
  completed_at: "2025-01-01T00:00:03Z",
  metrics: {
    changed_files: 4,
    additions: 42,
    deletions: 8,
    requirement_coverage: 0.62,
    duration_ms: 3000,
  },
};
const projectTemplate = {
  id: "project-1",
  name: "Demo Service",
  slug: "demo-service",
  description: "Acceptance scope for a small FastAPI service.",
  default_branch: "main",
  repository_provider: "local",
  repository_url: null,
  created_at: "2025-01-01T00:00:00Z",
  analyses_count: 1,
  latest_verdict: "warn",
};
const finding = {
  id: "finding-1",
  analysis_run_id: "analysis-1",
  category: "security",
  severity: "high",
  title: "Shell execution accepts untrusted input",
  description: "A shell-enabled subprocess was introduced.",
  file_path: "app/service.py",
  start_line: 44,
  rule_id: "python-shell-true",
  remediation: "Pass a validated argument array without a shell.",
  evidence: { call: "subprocess.run", value: "[REDACTED]" },
  fingerprint: "safe-fingerprint",
  status: "open",
};

export interface MockState {
  projects: (typeof projectTemplate)[];
  currentUser: typeof owner;
  findingStatus: string;
}

export async function installMockApi(
  page: Page,
  options: { viewer?: boolean; seededProject?: boolean } = {},
) {
  const state: MockState = {
    projects: options.seededProject ? [projectTemplate] : [],
    currentUser: options.viewer ? viewer : owner,
    findingStatus: "open",
  };

  await page.route("**/api/v1/**", async (route) => handleRoute(route, state));
  return state;
}

async function handleRoute(route: Route, state: MockState) {
  const request = route.request();
  const url = new URL(request.url());
  const path = url.pathname.replace(/^\/api\/v1/, "");
  const method = request.method();
  const json = (value: unknown, status = 200) =>
    route.fulfill({ status, contentType: "application/json", body: JSON.stringify(value) });
  const page = <T>(items: T[]) => ({
    items,
    total: items.length,
    page: 1,
    page_size: 100,
    pages: 1,
  });

  if (path === "/auth/demo" && method === "POST")
    return json({
      access_token: "access",
      refresh_token: "refresh",
      token_type: "bearer",
      user: state.currentUser,
    });
  if (path === "/auth/login" && method === "POST")
    return json({
      access_token: "access",
      refresh_token: "refresh",
      token_type: "bearer",
      user: state.currentUser,
    });
  if (path === "/auth/me") return json(state.currentUser);
  if (path === "/auth/refresh" && method === "POST")
    return json({ access_token: "access-2", refresh_token: "refresh", token_type: "bearer" });
  if (path === "/projects" && method === "GET") return json(page(state.projects));
  if (path === "/projects" && method === "POST") {
    const body = request.postDataJSON() as Record<string, string>;
    const created = {
      ...projectTemplate,
      name: body.name ?? projectTemplate.name,
      description: body.description ?? "",
      slug: body.slug || "demo-service",
      analyses_count: 0,
      latest_verdict: "unknown" as const,
    };
    state.projects = [created];
    return json(created, 201);
  }
  if (/^\/projects\/[^/]+$/.test(path) && method === "GET")
    return json(state.projects[0] ?? projectTemplate);
  if (/^\/projects\/[^/]+$/.test(path) && method === "DELETE") {
    if (state.currentUser.role === "viewer")
      return json({ error: { code: "forbidden", message: "Viewer access is read-only." } }, 403);
    state.projects = [];
    return route.fulfill({ status: 204 });
  }
  if (/^\/projects\/[^/]+\/analyses$/.test(path))
    return json(page(state.projects.length ? [analysis] : []));
  if (/^\/projects\/[^/]+\/analyses\/(demo|upload|github)$/.test(path) && method === "POST")
    return json({ ...analysis, status: "queued", verdict: "unknown", progress: 0 }, 202);
  if (path === "/analyses/analysis-1") return json(analysis);
  if (path === "/analyses/analysis-1/progress")
    return json({
      analysis_id: analysis.id,
      status: "completed",
      progress: 100,
      current_stage: "FINALIZE",
      stages: [
        { name: "PREPARE_SOURCE", status: "completed", duration_ms: 100 },
        { name: "FINALIZE", status: "completed", duration_ms: 80 },
      ],
    });
  if (path === "/analyses/analysis-1/events")
    return json(
      page([
        {
          id: "event-1",
          stage: "FINALIZE",
          level: "info",
          message: "Evidence bundle finalized",
          created_at: "2025-01-01T00:00:03Z",
        },
      ]),
    );
  if (path === "/analyses/analysis-1/cancel" && method === "POST")
    return json({ ...analysis, status: "cancelled" });
  if (path === "/analyses/analysis-1/findings")
    return json(page([{ ...finding, status: state.findingStatus }]));
  if (path === "/findings/finding-1" && method === "PATCH") {
    if (state.currentUser.role === "viewer")
      return json({ error: { code: "forbidden", message: "Viewer access is read-only." } }, 403);
    const body = request.postDataJSON() as { status: string };
    state.findingStatus = body.status;
    return json({ ...finding, status: body.status });
  }
  if (path === "/analyses/analysis-1/changed-files")
    return json(
      page([
        {
          id: "file-1",
          path: "app/service.py",
          change_type: "modified",
          additions: 22,
          deletions: 4,
          language: "Python",
          risk_score: 78,
          is_test: false,
          is_generated: false,
          finding_count: 1,
          requirement_count: 1,
          test_count: 0,
        },
      ]),
    );
  if (path === "/analyses/analysis-1/graph")
    return json({
      nodes: [
        { id: "node-1", label: "app.service", type: "file", changed: true, risk_score: 78 },
        {
          id: "node-2",
          label: "run_command",
          type: "symbol",
          blast_radius: true,
          file_path: "app/service.py",
        },
      ],
      edges: [
        { id: "edge-1", source: "node-1", target: "node-2", edge_type: "contains", confidence: 1 },
      ],
    });
  if (path === "/analyses/analysis-1/requirements")
    return json(
      page([
        {
          id: "requirement-1",
          external_id: "DEMO-1",
          title: "Expose a safe health endpoint",
          description: "The endpoint should be observable and safe.",
          acceptance_criteria: ["Returns a stable schema"],
          confidence: 0.62,
          coverage_score: 0.62,
          supported: true,
          changed_files: ["app/service.py"],
          changed_symbols: ["health"],
          tests: [],
        },
      ]),
    );
  if (path === "/analyses/analysis-1/tests")
    return json(
      page([
        {
          id: "test-1",
          command: "pytest -q",
          status: "passed",
          exit_code: 0,
          duration_ms: 420,
          stdout_excerpt: "5 passed",
          stderr_excerpt: "",
          timed_out: false,
          environment: { python: "3.12" },
          runner: "native",
        },
      ]),
    );
  if (path === "/analyses/analysis-1/policy-decisions")
    return json(
      page([
        {
          id: "decision-1",
          policy_name: "default",
          rule_id: "requirement-coverage",
          outcome: "warn",
          explanation: "Coverage is below 70 percent.",
          observed_value: 0.62,
          expected_value: 0.7,
          operator: "gte",
          evidence_references: ["requirements.json"],
        },
      ]),
    );
  if (path === "/analyses/analysis-1/evidence")
    return json({
      schema_version: "1.0",
      verified: true,
      manifest: {
        schema_version: "1.0",
        tool_version: "0.1.0",
        generated_at: "2025-01-01T00:00:03Z",
      },
      artifacts: [
        {
          id: "artifact-1",
          artifact_type: "report",
          name: "analysis.json",
          content_type: "application/json",
          sha256: "a".repeat(64),
          size: 420,
          verified: true,
        },
        {
          id: "artifact-2",
          artifact_type: "report",
          name: "report.html",
          content_type: "text/html",
          sha256: "b".repeat(64),
          size: 840,
          verified: true,
        },
      ],
    });
  if (path === "/analyses/analysis-1/evidence/download")
    return route.fulfill({
      status: 200,
      contentType: "application/zip",
      headers: { "content-disposition": "attachment; filename=evidence.zip" },
      body: "mock-evidence-bundle",
    });
  if (path === "/audit-events")
    return json(
      page([
        {
          id: "audit-1",
          user_id: state.currentUser.id,
          user: state.currentUser,
          action: "analysis.created",
          resource_type: "analysis",
          resource_id: analysis.id,
          created_at: "2025-01-01T00:00:00Z",
        },
      ]),
    );
  if (path === "/policies") return json(page([{ name: "default", version: 1 }]));
  if (path === "/organizations/current")
    return json({ id: "org-1", name: "Demo Organization", slug: "demo-organization" });
  if (path === "/organizations/current/members") return json(page([state.currentUser]));
  if (path === "/system/public-config")
    return json({
      version: "0.1.0",
      environment: "test",
      demo_mode: true,
      github_token_configured: false,
      runner: "native",
      runner_available: true,
      semgrep_enabled: false,
      semgrep_available: false,
      task_backend: "inline",
      llm_enabled: false,
    });
  if (path === "/version") return json({ version: "0.1.0" });
  if (path === "/ready") return json({ status: "ready" });
  return json({ error: { code: "not_found", message: `No E2E route for ${method} ${path}` } }, 404);
}
