import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ChevronDown, ChevronUp, FileWarning, Filter } from "lucide-react";
import { useMemo, useState } from "react";
import { useOutletContext } from "react-router-dom";

import { api } from "../../api/client";
import type { Finding } from "../../api/types";
import { canReviewFindings, useAuthStore } from "../../auth/store";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  SeverityBadge,
} from "../../components/ui";
import type { AnalysisOutletContext } from "../AnalysisPage";

export function FindingsTab() {
  const { analysis } = useOutletContext<AnalysisOutletContext>();
  const queryClient = useQueryClient();
  const role = useAuthStore((state) => state.user?.role);
  const [severity, setSeverity] = useState("");
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ["analysis", analysis.id, "findings"],
    queryFn: () => api.analyses.findings(analysis.id, { page_size: 200 }),
  });
  const update = useMutation({
    mutationFn: ({ id, status: nextStatus }: { id: string; status: Finding["status"] }) =>
      api.findings.update(id, nextStatus),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["analysis", analysis.id, "findings"] });
    },
  });
  const categories = useMemo(
    () => Array.from(new Set((query.data?.items ?? []).map((finding) => finding.category))).sort(),
    [query.data?.items],
  );
  const findings = useMemo(
    () =>
      (query.data?.items ?? []).filter(
        (finding) =>
          (!severity || finding.severity === severity) &&
          (!category || finding.category === category) &&
          (!status || finding.status === status),
      ),
    [category, query.data?.items, severity, status],
  );

  if (query.isLoading) return <LoadingState label="Loading findings…" />;
  if (query.isError) return <ErrorState error={query.error} retry={() => void query.refetch()} />;

  return (
    <div className="tab-stack">
      <Card className="finding-summary">
        {(["critical", "high", "medium", "low", "info"] as const).map((level) => (
          <button
            key={level}
            className={severity === level ? "selected" : ""}
            onClick={() => setSeverity(severity === level ? "" : level)}
          >
            <span className={`severity-pip severity-pip--${level}`} />
            <strong>
              {query.data?.items.filter((finding) => finding.severity === level).length ?? 0}
            </strong>
            <small>{level}</small>
          </button>
        ))}
      </Card>
      <Card className="toolbar-card">
        <span className="toolbar-label">
          <Filter size={16} /> Filters
        </span>
        <div className="filters filters--inline">
          <label>
            <span>Severity</span>
            <select value={severity} onChange={(event) => setSeverity(event.target.value)}>
              <option value="">All severities</option>
              {["critical", "high", "medium", "low", "info"].map((item) => (
                <option key={item}>{item}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Category</span>
            <select value={category} onChange={(event) => setCategory(event.target.value)}>
              <option value="">All categories</option>
              {categories.map((item) => (
                <option key={item}>{item}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Status</span>
            <select value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="">All statuses</option>
              <option value="open">Open</option>
              <option value="acknowledged">Acknowledged</option>
              <option value="resolved">Resolved</option>
              <option value="false_positive">False positive</option>
            </select>
          </label>
        </div>
        <span className="result-count">{findings.length} findings</span>
      </Card>
      {!findings.length ? (
        <EmptyState
          icon={<CheckCircle2 />}
          title="No findings match"
          description={
            query.data?.total
              ? "Adjust the active filters to restore evidence signals."
              : "No findings were emitted by this analysis."
          }
        />
      ) : (
        <div className="finding-list">
          {findings.map((finding) => (
            <FindingCard
              key={finding.id}
              finding={finding}
              expanded={expanded === finding.id}
              onToggle={() => setExpanded(expanded === finding.id ? null : finding.id)}
              canReview={canReviewFindings(role)}
              updating={update.isPending && update.variables?.id === finding.id}
              onStatus={(nextStatus) => update.mutate({ id: finding.id, status: nextStatus })}
            />
          ))}
        </div>
      )}
      {update.error ? (
        <div className="form-error" role="alert">
          {update.error.message}
        </div>
      ) : null}
    </div>
  );
}

function FindingCard({
  finding,
  expanded,
  onToggle,
  canReview,
  updating,
  onStatus,
}: {
  finding: Finding;
  expanded: boolean;
  onToggle: () => void;
  canReview: boolean;
  updating: boolean;
  onStatus: (status: Finding["status"]) => void;
}) {
  const evidence =
    typeof finding.evidence === "string"
      ? finding.evidence
      : finding.evidence
        ? JSON.stringify(finding.evidence, null, 2)
        : "No additional structured evidence.";
  return (
    <Card className={`finding-card finding-card--${finding.severity}`}>
      <button className="finding-card__main" onClick={onToggle} aria-expanded={expanded}>
        <span className={`finding-icon finding-icon--${finding.severity}`}>
          <FileWarning size={18} />
        </span>
        <div>
          <div className="finding-labels">
            <SeverityBadge severity={finding.severity} />
            <Badge tone="neutral">{finding.category}</Badge>
            <Badge
              tone={
                finding.status === "resolved" || finding.status === "false_positive"
                  ? "pass"
                  : "neutral"
              }
            >
              {finding.status.replaceAll("_", " ")}
            </Badge>
          </div>
          <h2>{finding.title}</h2>
          <p>{finding.description}</p>
          {finding.file_path ? (
            <code>
              {finding.file_path}
              {finding.start_line
                ? `:${finding.start_line}${finding.end_line && finding.end_line !== finding.start_line ? `–${finding.end_line}` : ""}`
                : ""}
            </code>
          ) : null}
        </div>
        {expanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
      </button>
      {expanded ? (
        <div className="finding-details">
          <div>
            <h3>Evidence</h3>
            <pre>{evidence}</pre>
          </div>
          <div>
            <h3>Remediation</h3>
            <p>
              {finding.remediation ||
                "Review the evidence in context and add a documented mitigation if the behavior is intentional."}
            </p>
            {finding.rule_id ? (
              <p>
                <strong>Rule:</strong> <code>{finding.rule_id}</code>
              </p>
            ) : null}
            {finding.fingerprint ? (
              <p>
                <strong>Fingerprint:</strong> <code>{finding.fingerprint}</code>
              </p>
            ) : null}
          </div>
          <label className="field finding-status">
            <span>Review status</span>
            <select
              value={finding.status}
              disabled={!canReview || updating}
              onChange={(event) => onStatus(event.target.value as Finding["status"])}
            >
              <option value="open">Open</option>
              <option value="acknowledged">Acknowledged</option>
              <option value="resolved">Resolved</option>
              <option value="false_positive">False positive</option>
            </select>
            {!canReview ? (
              <small className="field-hint">Your viewer role is read-only.</small>
            ) : null}
          </label>
        </div>
      ) : null}
    </Card>
  );
}
