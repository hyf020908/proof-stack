import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Download, FileArchive, FileKey2, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useOutletContext } from "react-router-dom";

import { api, downloadEvidence } from "../../api/client";
import { formatBytes, formatDate } from "../../components/format";
import { Badge, Button, Card, EmptyState, ErrorState, LoadingState } from "../../components/ui";
import type { AnalysisOutletContext } from "../AnalysisPage";

export function EvidenceTab() {
  const { analysis } = useOutletContext<AnalysisOutletContext>();
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ["analysis", analysis.id, "evidence"],
    queryFn: () => api.analyses.evidence(analysis.id),
  });
  if (query.isLoading) return <LoadingState label="Loading evidence manifest…" />;
  if (query.isError) return <ErrorState error={query.error} retry={() => void query.refetch()} />;
  if (!query.data?.artifacts.length)
    return (
      <EmptyState
        icon={<FileArchive />}
        title="Evidence bundle is not available"
        description="The analysis may still be active or may have failed before the bundle stage."
      />
    );
  const manifest = query.data.manifest ?? {};
  const startDownload = async () => {
    setDownloading(true);
    setDownloadError(null);
    try {
      await downloadEvidence(analysis.id);
    } catch (error) {
      setDownloadError(error instanceof Error ? error.message : "Download failed.");
    } finally {
      setDownloading(false);
    }
  };
  const schemaVersion = query.data.schema_version ?? displayManifestValue(manifest.schema_version);
  return (
    <div className="tab-stack">
      <Card className="evidence-hero">
        <span className="evidence-hero__icon">
          <ShieldCheck size={24} />
        </span>
        <div>
          <p className="eyebrow">Portable acceptance record</p>
          <h2>
            {query.data.verified === false
              ? "Bundle verification needs attention"
              : "Evidence manifest verified"}
          </h2>
          <p>
            Stable JSON, offline HTML, Markdown summary, and SHA-256 checksums preserve the full
            acceptance chain without secrets.
          </p>
          <div>
            <Badge tone={query.data.verified === false ? "fail" : "pass"}>
              {query.data.verified === false ? "checksum issue" : "checksums valid"}
            </Badge>
            <Badge tone="neutral">schema {schemaVersion === "—" ? "1" : schemaVersion}</Badge>
          </div>
        </div>
        <Button loading={downloading} onClick={() => void startDownload()}>
          <Download size={16} /> Download ZIP
        </Button>
      </Card>
      {downloadError ? (
        <div className="form-error" role="alert">
          {downloadError}
        </div>
      ) : null}
      <div className="evidence-layout">
        <Card className="artifact-card">
          <div className="section-heading">
            <div>
              <h2>Bundle artifacts</h2>
              <p>{query.data.artifacts.length} checksummed files</p>
            </div>
          </div>
          <div className="artifact-list">
            {query.data.artifacts.map((artifact) => (
              <div key={artifact.id ?? artifact.name}>
                <span>
                  <FileKey2 size={17} />
                </span>
                <div>
                  <strong>{artifact.name}</strong>
                  <small>
                    {artifact.content_type} · {formatBytes(artifact.size)}
                  </small>
                </div>
                <code title={artifact.sha256}>{artifact.sha256}</code>
                {artifact.verified === false ? (
                  <Badge tone="fail">mismatch</Badge>
                ) : (
                  <CheckCircle2 size={17} className="success-icon" />
                )}
              </div>
            ))}
          </div>
        </Card>
        <Card className="manifest-card">
          <div className="section-heading">
            <div>
              <h2>Manifest</h2>
              <p>Safe execution and input summary</p>
            </div>
          </div>
          <dl>
            {Object.entries(manifest)
              .slice(0, 16)
              .map(([key, value]) => (
                <div key={key}>
                  <dt>{key.replaceAll("_", " ")}</dt>
                  <dd>
                    {key.endsWith("_at") && typeof value === "string"
                      ? formatDate(value)
                      : displayManifestValue(value)}
                  </dd>
                </div>
              ))}
          </dl>
          <p className="manifest-note">
            Sensitive tokens, passwords, connection strings, and full secret matches are excluded
            from bundle artifacts.
          </p>
        </Card>
      </div>
    </div>
  );
}

function displayManifestValue(value: unknown): string {
  if (value === undefined || value === null) return "—";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value) ?? "—";
}
