import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  FileCode2,
  FlaskConical,
  ShieldAlert,
  Target,
} from "lucide-react";
import { Link, useOutletContext } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { api } from "../../api/client";
import { formatPercent } from "../../components/format";
import { Card, MetricCard, SeverityBadge, VerdictBadge } from "../../components/ui";
import type { AnalysisOutletContext } from "../AnalysisPage";

export function OverviewTab() {
  const { analysis } = useOutletContext<AnalysisOutletContext>();
  const findings = useQuery({
    queryKey: ["analysis", analysis.id, "findings", "overview"],
    queryFn: () => api.analyses.findings(analysis.id, { page_size: 100 }),
  });
  const files = useQuery({
    queryKey: ["analysis", analysis.id, "files"],
    queryFn: () => api.analyses.files(analysis.id),
  });
  const requirements = useQuery({
    queryKey: ["analysis", analysis.id, "requirements"],
    queryFn: () => api.analyses.requirements(analysis.id),
  });
  const tests = useQuery({
    queryKey: ["analysis", analysis.id, "tests"],
    queryFn: () => api.analyses.tests(analysis.id),
  });
  const policies = useQuery({
    queryKey: ["analysis", analysis.id, "policies"],
    queryFn: () => api.analyses.policies(analysis.id),
  });

  const allFindings = findings.data?.items ?? [];
  const severe = allFindings.filter(
    (finding) => finding.severity === "critical" || finding.severity === "high",
  );
  const counts = ["critical", "high", "medium", "low", "info"].map((severity) => ({
    severity,
    count: allFindings.filter((finding) => finding.severity === severity).length,
  }));
  const requirementCoverage =
    analysis.metrics?.requirement_coverage ??
    (requirements.data?.items.length
      ? requirements.data.items.reduce(
          (sum, item) => sum + (item.coverage_score ?? item.confidence ?? 0),
          0,
        ) / requirements.data.items.length
      : 0);
  const passedTests = tests.data?.items.filter((test) => test.status === "passed").length ?? 0;

  return (
    <div className="tab-stack">
      <section className="verdict-hero glass-card">
        <div
          className={`risk-ring risk-ring--${analysis.verdict}`}
          style={
            {
              "--risk": `${Math.min(100, Math.max(0, analysis.risk_score)) * 3.6}deg`,
            } as React.CSSProperties
          }
        >
          <span>
            <strong>{Math.round(analysis.risk_score)}</strong>
            <small>risk / 100</small>
          </span>
        </div>
        <div className="verdict-hero__copy">
          <p className="eyebrow">Explainable decision</p>
          <h2>
            <VerdictBadge verdict={analysis.verdict} />{" "}
            {analysis.verdict === "pass"
              ? "Evidence supports acceptance"
              : analysis.verdict === "warn"
                ? "Review before acceptance"
                : analysis.verdict === "fail"
                  ? "Acceptance is blocked"
                  : "Decision is not available"}
          </h2>
          <p>
            {analysis.verdict === "fail"
              ? "One or more policy rules produced a blocking decision. Review the related findings and validation evidence."
              : analysis.verdict === "warn"
                ? "The change has usable evidence, with gaps that need a human decision."
                : "The decision combines deterministic risk components and explicit policy rules."}
          </p>
          <div className="verdict-hero__links">
            <Link to="policies">Inspect policy decisions</Link>
            <Link to="evidence">Verify evidence bundle</Link>
          </div>
        </div>
      </section>

      <section className="metric-grid metric-grid--five">
        <MetricCard
          label="Changed files"
          value={analysis.metrics?.changed_files ?? files.data?.total ?? "—"}
          detail={`${analysis.metrics?.additions ?? 0} additions · ${analysis.metrics?.deletions ?? 0} deletions`}
          icon={<FileCode2 size={18} />}
        />
        <MetricCard
          label="Requirements"
          value={formatPercent(requirementCoverage)}
          detail="Evidence coverage"
          icon={<Target size={18} />}
          tone={requirementCoverage >= 0.7 ? "pass" : "warn"}
        />
        <MetricCard
          label="Validation"
          value={passedTests}
          detail={`${tests.data?.total ?? 0} executions`}
          icon={<FlaskConical size={18} />}
          tone={passedTests ? "pass" : "warn"}
        />
        <MetricCard
          label="Severe findings"
          value={severe.length}
          detail="Critical and high"
          icon={<ShieldAlert size={18} />}
          tone={severe.length ? "fail" : "pass"}
        />
        <MetricCard
          label="Policy blocks"
          value={
            policies.data?.items.filter((decision) => decision.outcome === "fail").length ?? "—"
          }
          detail={`${policies.data?.total ?? 0} rules evaluated`}
          icon={<CheckCircle2 size={18} />}
        />
      </section>

      <div className="overview-grid">
        <Card className="chart-card">
          <div className="section-heading">
            <div>
              <h2>Finding severity</h2>
              <p>Open and reviewed evidence signals</p>
            </div>
          </div>
          <div className="chart-frame chart-frame--short">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={counts} margin={{ top: 8, left: -24, right: 0 }}>
                <CartesianGrid strokeDasharray="4 6" vertical={false} stroke="var(--chart-grid)" />
                <XAxis
                  dataKey="severity"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "var(--text-muted)", fontSize: 11 }}
                />
                <YAxis
                  allowDecimals={false}
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "var(--text-muted)", fontSize: 11 }}
                />
                <Tooltip
                  contentStyle={{
                    background: "var(--surface-solid)",
                    border: "1px solid var(--line)",
                    borderRadius: 12,
                  }}
                />
                <Bar dataKey="count" fill="#f2674e" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card className="blocker-card">
          <div className="section-heading">
            <div>
              <h2>Primary review items</h2>
              <p>Highest-severity evidence first</p>
            </div>
            <Link className="text-link" to="findings">
              All findings
            </Link>
          </div>
          <div className="blocker-list">
            {severe.slice(0, 5).map((finding) => (
              <article key={finding.id}>
                <span className={`finding-mark finding-mark--${finding.severity}`}>
                  <AlertTriangle size={15} />
                </span>
                <div>
                  <div>
                    <SeverityBadge severity={finding.severity} />
                    <small>{finding.category}</small>
                  </div>
                  <strong>{finding.title}</strong>
                  <p>
                    {finding.file_path
                      ? `${finding.file_path}${finding.start_line ? `:${finding.start_line}` : ""}`
                      : finding.description}
                  </p>
                </div>
              </article>
            ))}
            {!findings.isLoading && severe.length === 0 ? (
              <div className="small-empty">
                <CheckCircle2 size={22} />
                <strong>No critical or high findings</strong>
                <p>Review lower-severity evidence for context.</p>
              </div>
            ) : null}
            {findings.isError ? (
              <p className="muted">Finding evidence could not be loaded.</p>
            ) : null}
          </div>
        </Card>
      </div>
    </div>
  );
}
