import { useQuery } from "@tanstack/react-query";
import { FileClock, Filter } from "lucide-react";
import { useState } from "react";

import { api } from "../api/client";
import { formatDate, titleCase } from "../components/format";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  Pagination,
} from "../components/ui";

export function AuditPage() {
  const [page, setPage] = useState(1);
  const [action, setAction] = useState("");
  const [resourceType, setResourceType] = useState("");
  const pageSize = 20;
  const query = useQuery({
    queryKey: ["audit", page, action, resourceType],
    queryFn: () =>
      api.audit.list({
        page,
        page_size: pageSize,
        action: action || undefined,
        resource_type: resourceType || undefined,
      }),
  });
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Accountability trail"
        title="Audit log"
        description="Who changed what, when, and within which organization boundary."
      />
      <Card className="toolbar-card">
        <span className="toolbar-label">
          <Filter size={16} /> Filters
        </span>
        <div className="filters filters--inline">
          <label>
            <span>Action</span>
            <input
              value={action}
              onChange={(event) => {
                setPage(1);
                setAction(event.target.value);
              }}
              placeholder="e.g. analysis.created"
            />
          </label>
          <label>
            <span>Resource</span>
            <select
              value={resourceType}
              onChange={(event) => {
                setPage(1);
                setResourceType(event.target.value);
              }}
            >
              <option value="">All resources</option>
              <option value="organization">Organization</option>
              <option value="user">User</option>
              <option value="project">Project</option>
              <option value="analysis">Analysis</option>
              <option value="finding">Finding</option>
              <option value="evidence">Evidence</option>
            </select>
          </label>
        </div>
        <span className="result-count">{query.data?.total ?? 0} events</span>
      </Card>
      {query.isLoading ? <LoadingState label="Loading audit events…" /> : null}
      {query.isError ? <ErrorState error={query.error} retry={() => void query.refetch()} /> : null}
      {query.isSuccess && !query.data.items.length ? (
        <EmptyState
          icon={<FileClock />}
          title="No audit events match"
          description="Clear the filters or perform an auditable workspace action."
        />
      ) : null}
      {query.data?.items.length ? (
        <Card className="audit-list">
          <div className="audit-list__head">
            <span>Event</span>
            <span>Actor</span>
            <span>Resource</span>
            <span>Time</span>
          </div>
          {query.data.items.map((event) => (
            <article key={event.id}>
              <span className="audit-icon">
                <FileClock size={16} />
              </span>
              <div>
                <strong>{titleCase(event.action)}</strong>
                <small>{event.ip_address ? `From ${event.ip_address}` : "Origin protected"}</small>
              </div>
              <div>
                <strong>
                  {event.user?.display_name ??
                    event.user?.email ??
                    (event.user_id ? `User ${event.user_id.slice(0, 8)}` : "System")}
                </strong>
                <small>{event.user?.email}</small>
              </div>
              <div>
                <Badge tone="neutral">{event.resource_type}</Badge>
                <small>{event.resource_id?.slice(0, 12) ?? "—"}</small>
              </div>
              <time>{formatDate(event.created_at)}</time>
              {event.metadata && Object.keys(event.metadata).length ? (
                <details>
                  <summary>Metadata</summary>
                  <pre>{JSON.stringify(event.metadata, null, 2)}</pre>
                </details>
              ) : null}
            </article>
          ))}
        </Card>
      ) : null}
      {query.data ? (
        <Pagination page={page} pageSize={pageSize} total={query.data.total} onPage={setPage} />
      ) : null}
    </div>
  );
}
