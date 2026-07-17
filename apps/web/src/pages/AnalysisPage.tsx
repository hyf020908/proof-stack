import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  ArrowLeft,
  Download,
  FileCode2,
  FileKey2,
  Files,
  FlaskConical,
  GitFork,
  ListChecks,
  Scale,
  ShieldAlert,
} from "lucide-react";
import { Link, NavLink, Outlet, useParams } from "react-router-dom";

import { api, downloadEvidence } from "../api/client";
import type { AnalysisRun } from "../api/types";
import { formatDate } from "../components/format";
import {
  Button,
  ErrorState,
  LoadingState,
  PageHeader,
  StatusBadge,
  VerdictBadge,
  cx,
} from "../components/ui";

export interface AnalysisOutletContext {
  analysis: AnalysisRun;
}

const tabs = [
  { to: "", label: "Overview", icon: Activity, end: true },
  { to: "files", label: "Changed files", icon: Files },
  { to: "graph", label: "Impact graph", icon: GitFork },
  { to: "requirements", label: "Requirements", icon: ListChecks },
  { to: "findings", label: "Findings", icon: ShieldAlert },
  { to: "validation", label: "Validation", icon: FlaskConical },
  { to: "policies", label: "Policies", icon: Scale },
  { to: "evidence", label: "Evidence", icon: FileKey2 },
];

export function AnalysisPage() {
  const { analysisId = "" } = useParams();
  const analysis = useQuery({
    queryKey: ["analysis", analysisId],
    queryFn: () => api.analyses.get(analysisId),
    enabled: Boolean(analysisId),
  });

  if (analysis.isLoading) return <LoadingState label="Loading analysis evidence…" />;
  if (analysis.isError)
    return <ErrorState error={analysis.error} retry={() => void analysis.refetch()} />;
  if (!analysis.data) return null;
  const active = !["completed", "failed", "cancelled"].includes(analysis.data.status);

  return (
    <div className="page-stack analysis-page">
      <Link className="back-link" to={`/projects/${analysis.data.project_id}`}>
        <ArrowLeft size={15} /> Project history
      </Link>
      <PageHeader
        eyebrow={`${analysis.data.source_type} · ${formatDate(analysis.data.started_at ?? analysis.data.created_at)}`}
        title={analysis.data.source_reference || `Analysis ${analysis.data.id.slice(0, 12)}`}
        description={
          analysis.data.error_summary ||
          "Trace the evidence behind this change acceptance decision."
        }
        actions={
          <div className="header-action-group">
            <StatusBadge status={analysis.data.status} />
            <VerdictBadge verdict={analysis.data.verdict} />
            {active ? (
              <Link to={`/analyses/${analysisId}/progress`}>
                <Button variant="secondary">
                  <Activity size={16} /> Live progress
                </Button>
              </Link>
            ) : (
              <Button onClick={() => void downloadEvidence(analysisId)}>
                <Download size={16} /> Download bundle
              </Button>
            )}
          </div>
        }
      />
      <nav className="tabs" aria-label="Analysis evidence views">
        {tabs.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={label}
            to={to}
            end={end}
            className={({ isActive }) => cx("tab-link", isActive && "tab-link--active")}
          >
            <Icon size={16} />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>
      {analysis.data.status === "failed" ? (
        <div className="form-error">
          <FileCode2 size={17} />
          This run failed before all evidence could be collected. Available partial evidence remains
          visible.
        </div>
      ) : null}
      <Outlet context={{ analysis: analysis.data } satisfies AnalysisOutletContext} />
    </div>
  );
}
