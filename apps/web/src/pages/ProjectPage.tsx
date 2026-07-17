import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowUpRight, GitBranch, Play, Plus } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "../api/client";
import { canManageProjects, useAuthStore } from "../auth/store";
import { formatDate } from "../components/format";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  StatusBadge,
  VerdictBadge,
} from "../components/ui";

export function ProjectPage() {
  const { projectId = "" } = useParams();
  const navigate = useNavigate();
  const role = useAuthStore((state) => state.user?.role);
  const project = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => api.projects.get(projectId),
    enabled: Boolean(projectId),
  });
  const analyses = useQuery({
    queryKey: ["project", projectId, "analyses"],
    queryFn: () => api.analyses.list(projectId, { page_size: 100 }),
    enabled: Boolean(projectId),
  });

  if (project.isLoading) return <LoadingState label="Loading project…" />;
  if (project.isError)
    return <ErrorState error={project.error} retry={() => void project.refetch()} />;
  if (!project.data) return null;

  return (
    <div className="page-stack">
      <Link className="back-link" to="/projects">
        <ArrowLeft size={15} /> All projects
      </Link>
      <PageHeader
        eyebrow={project.data.repository_provider}
        title={project.data.name}
        description={
          project.data.description || "Evidence and acceptance history for this project."
        }
        actions={
          canManageProjects(role) ? (
            <Button onClick={() => void navigate(`/analyses/new?project=${projectId}`)}>
              <Plus size={16} /> New analysis
            </Button>
          ) : undefined
        }
      />
      <Card className="project-summary">
        <div>
          <small>Repository</small>
          {project.data.repository_url ? (
            <a href={project.data.repository_url} target="_blank" rel="noreferrer">
              {project.data.repository_url}
              <ArrowUpRight size={14} />
            </a>
          ) : (
            <strong>Uploaded and demo sources</strong>
          )}
        </div>
        <div>
          <small>Default branch</small>
          <strong>
            <GitBranch size={14} /> {project.data.default_branch}
          </strong>
        </div>
        <div>
          <small>Created</small>
          <strong>{formatDate(project.data.created_at)}</strong>
        </div>
        <div>
          <small>Project slug</small>
          <strong>{project.data.slug}</strong>
        </div>
      </Card>
      <section>
        <div className="section-heading">
          <div>
            <h2>Analysis history</h2>
            <p>A durable timeline of code acceptance decisions</p>
          </div>
        </div>
        {analyses.isLoading ? <LoadingState label="Loading analysis history…" /> : null}
        {analyses.isError ? (
          <ErrorState error={analyses.error} retry={() => void analyses.refetch()} />
        ) : null}
        {analyses.data && !analyses.data.items.length ? (
          <EmptyState
            icon={<Play />}
            title="No analysis history"
            description="Run the deterministic demo or provide a source archive, diff, or public GitHub URL."
            action={
              canManageProjects(role) ? (
                <Button onClick={() => void navigate(`/analyses/new?project=${projectId}`)}>
                  Run first analysis
                </Button>
              ) : undefined
            }
          />
        ) : null}
        {analyses.data?.items.length ? (
          <Card className="table-card">
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Source</th>
                    <th>Status</th>
                    <th>Verdict</th>
                    <th>Risk</th>
                    <th>Stage</th>
                    <th>Started</th>
                    <th>
                      <span className="sr-only">Open</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {analyses.data.items.map((analysis) => (
                    <tr key={analysis.id}>
                      <td>
                        <Link className="table-primary" to={`/analyses/${analysis.id}`}>
                          {analysis.source_reference || analysis.source_type}
                        </Link>
                        <small>{analysis.id.slice(0, 12)}</small>
                      </td>
                      <td>
                        <StatusBadge status={analysis.status} />
                      </td>
                      <td>
                        <VerdictBadge verdict={analysis.verdict} />
                      </td>
                      <td>
                        <strong>{Math.round(analysis.risk_score)}</strong>
                        <small>/ 100</small>
                      </td>
                      <td>{analysis.current_stage?.replaceAll("_", " ") ?? "—"}</td>
                      <td>{formatDate(analysis.started_at ?? analysis.created_at)}</td>
                      <td>
                        <Link
                          className="icon-button"
                          to={`/analyses/${analysis.id}`}
                          aria-label="Open analysis"
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
        ) : null}
      </section>
    </div>
  );
}
