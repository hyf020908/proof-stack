import { useQuery } from "@tanstack/react-query";
import {
  ArrowUpRight,
  CircleCheck,
  Clock3,
  FileWarning,
  FolderKanban,
  Plus,
  ShieldAlert,
} from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { api } from "../api/client";
import { formatDate, formatDuration } from "../components/format";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  MetricCard,
  PageHeader,
  VerdictBadge,
} from "../components/ui";

const verdictColors: Record<string, string> = {
  pass: "#35a873",
  warn: "#e69a2e",
  fail: "#df4b55",
  unknown: "#8f8a92",
};

const getAllAnalyses = async () => {
  const projects = await api.projects.list({ page_size: 100 });
  const collections = await Promise.all(
    projects.items.map((project) => api.analyses.list(project.id, { page_size: 100 })),
  );
  return {
    projects: projects.items,
    analyses: collections.flatMap((page) => page.items),
  };
};

export function DashboardPage() {
  const navigate = useNavigate();
  const workspace = useQuery({ queryKey: ["dashboard"], queryFn: getAllAnalyses });
  const audit = useQuery({
    queryKey: ["audit", "recent"],
    queryFn: () => api.audit.list({ page: 1, page_size: 5 }),
  });

  if (workspace.isLoading) return <DashboardSkeleton />;
  if (workspace.isError)
    return <ErrorState error={workspace.error} retry={() => void workspace.refetch()} />;

  const analyses = [...(workspace.data?.analyses ?? [])].sort((a, b) =>
    String(b.started_at ?? b.created_at).localeCompare(String(a.started_at ?? a.created_at)),
  );
  const completed = analyses.filter((analysis) => analysis.status === "completed");
  const verdictData = ["pass", "warn", "fail", "unknown"].map((name) => ({
    name,
    value: completed.filter((analysis) => analysis.verdict === name).length,
  }));
  const trend = analyses
    .filter((analysis) => analysis.started_at || analysis.created_at)
    .slice(0, 12)
    .reverse()
    .map((analysis, index) => ({
      name: `#${index + 1}`,
      risk: analysis.risk_score ?? 0,
      date: formatDate(analysis.started_at ?? analysis.created_at),
    }));
  const findingCount = analyses.reduce(
    (sum, analysis) =>
      sum + (analysis.metrics?.critical_findings ?? 0) + (analysis.metrics?.high_findings ?? 0),
    0,
  );
  const durations = completed
    .map((analysis) => analysis.metrics?.duration_ms)
    .filter((value): value is number => value !== undefined);
  const averageDuration = durations.length
    ? durations.reduce((sum, value) => sum + value, 0) / durations.length
    : undefined;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Evidence workspace"
        title="What is ready to merge?"
        description="A live view of acceptance signals across every project in your organization."
        actions={
          <Button onClick={() => void navigate("/analyses/new")}>
            <Plus size={16} /> New analysis
          </Button>
        }
      />

      <section className="metric-grid" aria-label="Workspace metrics">
        <MetricCard
          label="Projects"
          value={workspace.data?.projects.length ?? 0}
          detail="Active evidence scopes"
          icon={<FolderKanban size={18} />}
        />
        <MetricCard
          label="Completed runs"
          value={completed.length}
          detail={`${analyses.filter((run) => !["completed", "failed", "cancelled"].includes(run.status)).length} currently active`}
          icon={<CircleCheck size={18} />}
          tone="pass"
        />
        <MetricCard
          label="Critical + high"
          value={findingCount}
          detail="Across visible analyses"
          icon={<ShieldAlert size={18} />}
          tone={findingCount ? "fail" : "pass"}
        />
        <MetricCard
          label="Average duration"
          value={formatDuration(averageDuration)}
          detail="Completed analyses"
          icon={<Clock3 size={18} />}
        />
      </section>

      {analyses.length === 0 ? (
        <EmptyState
          icon={<FileWarning />}
          title="No acceptance evidence yet"
          description="Create a project, then run the built-in demo to see the full deterministic pipeline."
          action={
            <Button onClick={() => void navigate("/projects")}>Create your first project</Button>
          }
        />
      ) : (
        <section className="dashboard-grid">
          <Card className="chart-card chart-card--wide">
            <div className="section-heading">
              <div>
                <h2>Risk trajectory</h2>
                <p>Deterministic score from recent change evidence</p>
              </div>
              <span className="chart-key">
                <i /> Risk score
              </span>
            </div>
            <div className="chart-frame" aria-label="Risk score trend chart">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={trend} margin={{ top: 8, right: 4, left: -24, bottom: 0 }}>
                  <defs>
                    <linearGradient id="risk-fill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#f2674e" stopOpacity={0.34} />
                      <stop offset="95%" stopColor="#f2674e" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid
                    strokeDasharray="4 6"
                    vertical={false}
                    stroke="var(--chart-grid)"
                  />
                  <XAxis
                    dataKey="name"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: "var(--text-muted)", fontSize: 12 }}
                  />
                  <YAxis
                    domain={[0, 100]}
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: "var(--text-muted)", fontSize: 12 }}
                  />
                  <Tooltip
                    contentStyle={{
                      background: "var(--surface-solid)",
                      border: "1px solid var(--line)",
                      borderRadius: 12,
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="risk"
                    stroke="#f2674e"
                    fill="url(#risk-fill)"
                    strokeWidth={2.2}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <Card className="chart-card">
            <div className="section-heading">
              <div>
                <h2>Verdict mix</h2>
                <p>Completed analyses</p>
              </div>
            </div>
            <div className="donut-layout">
              <div className="donut-frame">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={verdictData}
                      dataKey="value"
                      nameKey="name"
                      innerRadius={48}
                      outerRadius={68}
                      paddingAngle={3}
                    >
                      {verdictData.map((entry) => (
                        <Cell key={entry.name} fill={verdictColors[entry.name]} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{
                        background: "var(--surface-solid)",
                        border: "1px solid var(--line)",
                        borderRadius: 12,
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>
                <span>
                  <strong>{completed.length}</strong>
                  <small>runs</small>
                </span>
              </div>
              <div className="legend-list">
                {verdictData.map((entry) => (
                  <div key={entry.name}>
                    <i style={{ background: verdictColors[entry.name] }} />
                    <span>{entry.name}</span>
                    <strong>{entry.value}</strong>
                  </div>
                ))}
              </div>
            </div>
          </Card>

          <Card className="table-card chart-card--wide">
            <div className="section-heading">
              <div>
                <h2>Recent analyses</h2>
                <p>The newest acceptance decisions</p>
              </div>
              <Link className="text-link" to="/analyses">
                View all <ArrowUpRight size={15} />
              </Link>
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Source</th>
                    <th>Status</th>
                    <th>Verdict</th>
                    <th>Risk</th>
                    <th>Started</th>
                    <th>
                      <span className="sr-only">Open</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {analyses.slice(0, 6).map((analysis) => (
                    <tr key={analysis.id}>
                      <td>
                        <Link className="table-primary" to={`/analyses/${analysis.id}`}>
                          {analysis.source_reference || analysis.source_type}
                        </Link>
                        <small>
                          {analysis.current_stage?.replaceAll("_", " ") ?? analysis.source_type}
                        </small>
                      </td>
                      <td>
                        <span className="status-inline">
                          <i className={`status-dot status-dot--${analysis.status}`} />
                          {analysis.status}
                        </span>
                      </td>
                      <td>
                        <VerdictBadge verdict={analysis.verdict} />
                      </td>
                      <td>
                        <strong>{Math.round(analysis.risk_score ?? 0)}</strong>
                        <small>/ 100</small>
                      </td>
                      <td>{formatDate(analysis.started_at ?? analysis.created_at)}</td>
                      <td>
                        <Link
                          className="icon-button"
                          aria-label="Open analysis"
                          to={`/analyses/${analysis.id}`}
                        >
                          <ArrowUpRight size={16} />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <Card className="activity-card">
            <div className="section-heading">
              <div>
                <h2>Recent audit</h2>
                <p>Accountable workspace changes</p>
              </div>
            </div>
            {audit.isError ? (
              <p className="muted">Audit events are temporarily unavailable.</p>
            ) : null}
            <div className="activity-list">
              {audit.data?.items.map((event) => (
                <div key={event.id} className="activity-item">
                  <span className="activity-mark" />
                  <div>
                    <strong>{event.action.replaceAll("_", " ")}</strong>
                    <p>
                      {event.resource_type} · {formatDate(event.created_at)}
                    </p>
                  </div>
                </div>
              ))}
              {!audit.isLoading && !audit.data?.items.length ? (
                <p className="muted">No audit events yet.</p>
              ) : null}
            </div>
          </Card>
        </section>
      )}
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div className="page-stack" aria-busy="true" aria-label="Loading dashboard">
      <div className="skeleton skeleton--header" />
      <div className="metric-grid">
        {Array.from({ length: 4 }, (_, index) => (
          <div className="skeleton skeleton--metric" key={index} />
        ))}
      </div>
      <div className="dashboard-grid">
        <div className="skeleton skeleton--chart" />
        <div className="skeleton skeleton--chart" />
      </div>
    </div>
  );
}

export { getAllAnalyses };
