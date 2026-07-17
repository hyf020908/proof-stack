import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, BookOpenCheck, Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

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
import { getAllAnalyses } from "./DashboardPage";

export function AnalysesPage() {
  const navigate = useNavigate();
  const [status, setStatus] = useState("");
  const [verdict, setVerdict] = useState("");
  const query = useQuery({ queryKey: ["all-analyses"], queryFn: getAllAnalyses });
  const projects = useMemo(
    () => new Map(query.data?.projects.map((project) => [project.id, project.name])),
    [query.data?.projects],
  );
  const rows = (query.data?.analyses ?? []).filter(
    (analysis) =>
      (!status || analysis.status === status) && (!verdict || analysis.verdict === verdict),
  );

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Acceptance runs"
        title="Analyses"
        description="Every decision keeps the evidence that produced it."
        actions={
          <Button onClick={() => void navigate("/analyses/new")}>
            <Plus size={16} /> New analysis
          </Button>
        }
      />
      <Card className="toolbar-card">
        <div className="filters">
          <label>
            <span>Status</span>
            <select value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="">All statuses</option>
              <option value="queued">Queued</option>
              <option value="analyzing">Analyzing</option>
              <option value="testing">Testing</option>
              <option value="completed">Completed</option>
              <option value="failed">Failed</option>
              <option value="cancelled">Cancelled</option>
            </select>
          </label>
          <label>
            <span>Verdict</span>
            <select value={verdict} onChange={(event) => setVerdict(event.target.value)}>
              <option value="">All verdicts</option>
              <option value="pass">Pass</option>
              <option value="warn">Warn</option>
              <option value="fail">Fail</option>
              <option value="unknown">Unknown</option>
            </select>
          </label>
        </div>
      </Card>
      {query.isLoading ? <LoadingState label="Loading acceptance runs…" /> : null}
      {query.isError ? <ErrorState error={query.error} retry={() => void query.refetch()} /> : null}
      {query.isSuccess && rows.length === 0 ? (
        <EmptyState
          icon={<BookOpenCheck />}
          title="No analyses match"
          description="Adjust the filters or run a new analysis."
          action={<Button onClick={() => void navigate("/analyses/new")}>Start analysis</Button>}
        />
      ) : null}
      {rows.length ? (
        <Card className="table-card">
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Analysis</th>
                  <th>Project</th>
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
                {rows.map((analysis) => (
                  <tr key={analysis.id}>
                    <td>
                      <Link className="table-primary" to={`/analyses/${analysis.id}`}>
                        {analysis.source_reference || `${analysis.source_type} source`}
                      </Link>
                      <small>{analysis.id.slice(0, 12)}</small>
                    </td>
                    <td>{projects.get(analysis.project_id) ?? "Unknown project"}</td>
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
    </div>
  );
}
