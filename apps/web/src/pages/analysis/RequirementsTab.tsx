import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, CircleDashed, FileCode2, FlaskConical, ListChecks } from "lucide-react";
import { useOutletContext } from "react-router-dom";

import { api } from "../../api/client";
import type { Requirement } from "../../api/types";
import { formatPercent, getStringList } from "../../components/format";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  ProgressBar,
} from "../../components/ui";
import type { AnalysisOutletContext } from "../AnalysisPage";

export function RequirementsTab() {
  const { analysis } = useOutletContext<AnalysisOutletContext>();
  const query = useQuery({
    queryKey: ["analysis", analysis.id, "requirements"],
    queryFn: () => api.analyses.requirements(analysis.id),
  });
  if (query.isLoading) return <LoadingState label="Mapping requirement evidence…" />;
  if (query.isError) return <ErrorState error={query.error} retry={() => void query.refetch()} />;
  if (!query.data?.items.length)
    return (
      <EmptyState
        icon={<ListChecks />}
        title="No explicit requirements"
        description="The analysis still evaluates source, security, tests, validation, and policy evidence. Add requirements in a future run to measure intent coverage."
      />
    );
  const average =
    query.data.items.reduce((sum, requirement) => sum + coverage(requirement), 0) /
    query.data.items.length;
  const unsupported = query.data.items.filter(
    (requirement) => !requirement.supported && coverage(requirement) < 0.35,
  ).length;

  return (
    <div className="tab-stack">
      <Card className="coverage-summary">
        <div>
          <p className="eyebrow">Requirement evidence</p>
          <h2>{formatPercent(average)} covered</h2>
          <p>
            {query.data.total - unsupported} of {query.data.total} requirements have meaningful
            supporting evidence.
          </p>
        </div>
        <div
          className="coverage-ring"
          style={
            { "--coverage": `${Math.min(100, average * 100) * 3.6}deg` } as React.CSSProperties
          }
        >
          <strong>{formatPercent(average)}</strong>
        </div>
        <div className="coverage-stats">
          <span>
            <strong>{query.data.total}</strong>
            <small>Total</small>
          </span>
          <span>
            <strong>{unsupported}</strong>
            <small>Unsupported</small>
          </span>
        </div>
      </Card>
      <div className="requirement-list">
        {query.data.items.map((requirement) => (
          <RequirementCard key={requirement.id} requirement={requirement} />
        ))}
      </div>
    </div>
  );
}

const coverage = (requirement: Requirement) =>
  requirement.coverage_score ?? requirement.confidence ?? 0;

function RequirementCard({ requirement }: { requirement: Requirement }) {
  const score = coverage(requirement);
  const files = getStringList(requirement.changed_files);
  const symbols = getStringList(requirement.changed_symbols, ["qualified_name", "name"]);
  const tests = getStringList(requirement.tests, ["qualified_name", "name"]);
  const criteria = Array.isArray(requirement.acceptance_criteria)
    ? requirement.acceptance_criteria
    : (requirement.acceptance_criteria?.split("\n").filter(Boolean) ?? []);
  return (
    <Card className="requirement-card">
      <header>
        <span
          className={
            score >= 0.35 ? "requirement-state requirement-state--supported" : "requirement-state"
          }
        >
          {score >= 0.35 ? <CheckCircle2 size={18} /> : <CircleDashed size={18} />}
        </span>
        <div>
          <div>
            <Badge tone={score >= 0.7 ? "pass" : score >= 0.35 ? "warn" : "fail"}>
              {score >= 0.35 ? "supported" : "unsupported"}
            </Badge>
            {requirement.external_id ? <small>{requirement.external_id}</small> : null}
          </div>
          <h2>{requirement.title}</h2>
          <p>{requirement.description}</p>
        </div>
        <div className="requirement-score">
          <strong>{formatPercent(score)}</strong>
          <small>coverage</small>
        </div>
      </header>
      <ProgressBar value={score * 100} />
      {criteria.length ? (
        <div className="criteria-list">
          <h3>Acceptance criteria</h3>
          {criteria.map((item) => (
            <p key={item}>
              <CheckCircle2 size={14} />
              {item}
            </p>
          ))}
        </div>
      ) : null}
      <div className="linkage-grid">
        <EvidenceLinks icon={<FileCode2 size={15} />} label="Changed files" values={files} />
        <EvidenceLinks icon={<ListChecks size={15} />} label="Symbols" values={symbols} />
        <EvidenceLinks icon={<FlaskConical size={15} />} label="Tests" values={tests} />
      </div>
    </Card>
  );
}

function EvidenceLinks({
  icon,
  label,
  values,
}: {
  icon: React.ReactNode;
  label: string;
  values: string[];
}) {
  return (
    <div>
      <h3>
        {icon}
        {label}
        <span>{values.length}</span>
      </h3>
      {values.length ? (
        values.slice(0, 5).map((value) => <code key={value}>{value}</code>)
      ) : (
        <p>No linked evidence</p>
      )}
    </div>
  );
}
