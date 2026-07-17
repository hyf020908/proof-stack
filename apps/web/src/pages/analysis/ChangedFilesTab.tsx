import { useQuery } from "@tanstack/react-query";
import { FileCode2, FileSearch, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { useOutletContext } from "react-router-dom";

import { api } from "../../api/client";
import { Badge, Card, EmptyState, ErrorState, LoadingState } from "../../components/ui";
import type { AnalysisOutletContext } from "../AnalysisPage";

export function ChangedFilesTab() {
  const { analysis } = useOutletContext<AnalysisOutletContext>();
  const [search, setSearch] = useState("");
  const [risk, setRisk] = useState("");
  const [kind, setKind] = useState("");
  const query = useQuery({
    queryKey: ["analysis", analysis.id, "files"],
    queryFn: () => api.analyses.files(analysis.id),
  });
  const files = useMemo(
    () =>
      (query.data?.items ?? []).filter((file) => {
        const riskBand = file.risk_score >= 70 ? "high" : file.risk_score >= 35 ? "medium" : "low";
        return (
          (!search || file.path.toLowerCase().includes(search.toLowerCase())) &&
          (!risk || risk === riskBand) &&
          (!kind ||
            (kind === "test"
              ? file.is_test
              : kind === "generated"
                ? file.is_generated
                : file.language === kind || file.change_type === kind))
        );
      }),
    [kind, query.data?.items, risk, search],
  );

  if (query.isLoading) return <LoadingState label="Loading changed files…" />;
  if (query.isError) return <ErrorState error={query.error} retry={() => void query.refetch()} />;

  return (
    <div className="tab-stack">
      <Card className="toolbar-card">
        <label className="search-field">
          <Search size={17} />
          <span className="sr-only">Search changed files</span>
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Filter by path…"
          />
        </label>
        <div className="filters filters--inline">
          <label>
            <span>Risk</span>
            <select value={risk} onChange={(event) => setRisk(event.target.value)}>
              <option value="">All risk</option>
              <option value="high">High · 70+</option>
              <option value="medium">Medium · 35–69</option>
              <option value="low">Low · under 35</option>
            </select>
          </label>
          <label>
            <span>Type</span>
            <select value={kind} onChange={(event) => setKind(event.target.value)}>
              <option value="">All types</option>
              <option value="added">Added</option>
              <option value="modified">Modified</option>
              <option value="deleted">Deleted</option>
              <option value="renamed">Renamed</option>
              <option value="test">Tests</option>
              <option value="Python">Python</option>
            </select>
          </label>
        </div>
        <span className="result-count">
          {files.length} / {query.data?.total ?? 0} files
        </span>
      </Card>
      {!files.length ? (
        <EmptyState
          icon={<FileSearch />}
          title="No changed files match"
          description="Adjust the path, risk, or type filters."
        />
      ) : (
        <Card className="file-list-card">
          <div className="file-list-head">
            <span>Path</span>
            <span>Change</span>
            <span>Risk</span>
            <span>Evidence links</span>
          </div>
          {files.map((file) => (
            <article className="file-row" key={file.id}>
              <div className="file-name">
                <span className="file-icon">
                  <FileCode2 size={18} />
                </span>
                <div>
                  <strong>{file.path.split("/").pop()}</strong>
                  <small>
                    {file.path.includes("/") ? file.path.slice(0, file.path.lastIndexOf("/")) : "."}{" "}
                    · {file.language ?? "unknown"}
                  </small>
                </div>
              </div>
              <div>
                <Badge tone={file.change_type}>{file.change_type}</Badge>
                <span className="diff-stat">
                  <b>+{file.additions}</b>
                  <i>−{file.deletions}</i>
                </span>
              </div>
              <div className="risk-cell">
                <strong>{Math.round(file.risk_score)}</strong>
                <span className="mini-bar">
                  <i style={{ width: `${Math.min(100, file.risk_score)}%` }} />
                </span>
              </div>
              <div className="evidence-counts">
                <span>
                  <strong>{file.finding_count ?? 0}</strong> findings
                </span>
                <span>
                  <strong>{file.requirement_count ?? 0}</strong> requirements
                </span>
                <span>
                  <strong>{file.test_count ?? (file.is_test ? 1 : 0)}</strong> tests
                </span>
              </div>
            </article>
          ))}
        </Card>
      )}
    </div>
  );
}
