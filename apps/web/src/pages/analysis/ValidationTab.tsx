import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronUp, FlaskConical, Terminal } from "lucide-react";
import { useState } from "react";
import { useOutletContext } from "react-router-dom";

import { api } from "../../api/client";
import type { TestExecution } from "../../api/types";
import { formatDuration } from "../../components/format";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  StatusBadge,
} from "../../components/ui";
import type { AnalysisOutletContext } from "../AnalysisPage";

export function ValidationTab() {
  const { analysis } = useOutletContext<AnalysisOutletContext>();
  const [expanded, setExpanded] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ["analysis", analysis.id, "tests"],
    queryFn: () => api.analyses.tests(analysis.id),
  });
  if (query.isLoading) return <LoadingState label="Loading validation evidence…" />;
  if (query.isError) return <ErrorState error={query.error} retry={() => void query.refetch()} />;
  if (!query.data?.items.length)
    return (
      <EmptyState
        icon={<FlaskConical />}
        title="No validation executions"
        description="The runner may have been unavailable, or this analysis did not request a validation command. This is not treated as a pass."
      />
    );
  const results = query.data.items;
  return (
    <div className="tab-stack">
      <Card className="validation-summary">
        {["passed", "failed", "timed_out", "skipped", "unavailable"].map((status) => (
          <div key={status}>
            <StatusBadge status={status} />
            <strong>{results.filter((result) => result.status === status).length}</strong>
          </div>
        ))}
      </Card>
      <div className="validation-list">
        {results.map((result) => (
          <ValidationCard
            key={result.id}
            result={result}
            expanded={expanded === result.id}
            onToggle={() => setExpanded(expanded === result.id ? null : result.id)}
          />
        ))}
      </div>
    </div>
  );
}

function ValidationCard({
  result,
  expanded,
  onToggle,
}: {
  result: TestExecution;
  expanded: boolean;
  onToggle: () => void;
}) {
  const environment =
    typeof result.environment === "string"
      ? result.environment
      : result.environment
        ? Object.entries(result.environment)
            .map(([key, value]) => `${key}=${String(value)}`)
            .join(" · ")
        : "Filtered environment";
  return (
    <Card className={`validation-card validation-card--${result.status}`}>
      <button className="validation-card__head" onClick={onToggle} aria-expanded={expanded}>
        <span className="terminal-icon">
          <Terminal size={18} />
        </span>
        <div>
          <code>{result.command}</code>
          <span>
            <StatusBadge status={result.status} />
            <small>{formatDuration(result.duration_ms)}</small>
            <small>Exit {result.exit_code ?? "—"}</small>
            <small>{result.runner ?? "configured runner"}</small>
          </span>
        </div>
        {expanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
      </button>
      {expanded ? (
        <div className="validation-output">
          <div>
            <h3>
              Standard output <Badge tone="neutral">redacted excerpt</Badge>
            </h3>
            <pre>{result.stdout_excerpt || "No standard output captured."}</pre>
          </div>
          <div>
            <h3>
              Standard error <Badge tone="neutral">redacted excerpt</Badge>
            </h3>
            <pre>{result.stderr_excerpt || "No standard error captured."}</pre>
          </div>
          <p>
            <strong>Environment summary:</strong> {environment}
          </p>
          {result.timed_out ? (
            <div className="notice">
              The process exceeded its configured timeout and was terminated.
            </div>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}
