import { useQuery } from "@tanstack/react-query";
import { Check, Scale, X } from "lucide-react";
import { useOutletContext } from "react-router-dom";

import { api } from "../../api/client";
import { titleCase } from "../../components/format";
import { Badge, Card, EmptyState, ErrorState, LoadingState } from "../../components/ui";
import type { AnalysisOutletContext } from "../AnalysisPage";

export function PoliciesTab() {
  const { analysis } = useOutletContext<AnalysisOutletContext>();
  const query = useQuery({
    queryKey: ["analysis", analysis.id, "policies"],
    queryFn: () => api.analyses.policies(analysis.id),
  });
  if (query.isLoading) return <LoadingState label="Loading policy decisions…" />;
  if (query.isError) return <ErrorState error={query.error} retry={() => void query.refetch()} />;
  if (!query.data?.items.length)
    return (
      <EmptyState
        icon={<Scale />}
        title="No policy decisions"
        description="The analysis did not reach policy evaluation or no policy was configured."
      />
    );
  const blocks = query.data.items.filter((decision) => decision.outcome === "fail").length;
  return (
    <div className="tab-stack">
      <Card className="policy-summary">
        <div>
          <p className="eyebrow">Evaluated policy</p>
          <h2>{query.data.items[0]?.policy_name ?? "Default"}</h2>
        </div>
        <div>
          <strong>{query.data.total}</strong>
          <small>Rules evaluated</small>
        </div>
        <div>
          <strong>{blocks}</strong>
          <small>Blocking decisions</small>
        </div>
        <Badge
          tone={
            blocks
              ? "fail"
              : query.data.items.some((item) => item.outcome === "warn")
                ? "warn"
                : "pass"
          }
        >
          {analysis.verdict} verdict
        </Badge>
      </Card>
      <div className="policy-list">
        {query.data.items.map((decision) => (
          <Card className={`policy-card policy-card--${decision.outcome}`} key={decision.id}>
            <span className="policy-outcome">
              {decision.outcome === "fail" ? <X size={16} /> : <Check size={16} />}
            </span>
            <div className="policy-card__body">
              <div>
                <Badge tone={decision.outcome}>{decision.outcome}</Badge>
                <small>{decision.policy_name}</small>
              </div>
              <h2>{titleCase(decision.rule_id)}</h2>
              <p>{decision.explanation}</p>
              <dl>
                <div>
                  <dt>Observed</dt>
                  <dd>
                    <code>{display(decision.observed_value)}</code>
                  </dd>
                </div>
                <div>
                  <dt>Operator</dt>
                  <dd>
                    <code>{decision.operator ?? "—"}</code>
                  </dd>
                </div>
                <div>
                  <dt>Expected</dt>
                  <dd>
                    <code>{display(decision.expected_value)}</code>
                  </dd>
                </div>
              </dl>
              {decision.evidence_references?.length ? (
                <div className="evidence-refs">
                  <strong>Related evidence</strong>
                  {decision.evidence_references.map((reference) => (
                    <code key={reference}>{reference}</code>
                  ))}
                </div>
              ) : null}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}

const display = (value: unknown): string =>
  value === undefined ? "—" : typeof value === "string" ? value : JSON.stringify(value);
