import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Check,
  Circle,
  Clock3,
  ExternalLink,
  RotateCcw,
  Square,
  X,
} from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "../api/client";
import { formatDate, formatDuration, titleCase } from "../components/format";
import {
  Button,
  Card,
  ErrorState,
  LoadingState,
  PageHeader,
  ProgressBar,
  StatusBadge,
  cx,
} from "../components/ui";

const pipelineStages = [
  "PREPARE_SOURCE",
  "PARSE_DIFF",
  "DISCOVER_FILES",
  "EXTRACT_SYMBOLS",
  "BUILD_DEPENDENCY_GRAPH",
  "MAP_REQUIREMENTS",
  "ANALYZE_IMPACT",
  "ANALYZE_TEST_GAPS",
  "SCAN_SECURITY",
  "SCAN_DEPENDENCIES",
  "DETECT_CONFIG_CHANGES",
  "EXECUTE_VALIDATION",
  "EVALUATE_POLICIES",
  "BUILD_EVIDENCE",
  "FINALIZE",
];

const terminalStatuses = ["completed", "failed", "cancelled"];

export function AnalysisProgressPage() {
  const { analysisId = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const analysis = useQuery({
    queryKey: ["analysis", analysisId],
    queryFn: () => api.analyses.get(analysisId),
    enabled: Boolean(analysisId),
    refetchInterval: (query) =>
      terminalStatuses.includes(query.state.data?.status ?? "") ? false : 1200,
  });
  const progress = useQuery({
    queryKey: ["analysis", analysisId, "progress"],
    queryFn: () => api.analyses.progress(analysisId),
    enabled: Boolean(analysisId),
    refetchInterval: (query) =>
      terminalStatuses.includes(query.state.data?.status ?? "") ? false : 1000,
  });
  const events = useQuery({
    queryKey: ["analysis", analysisId, "events"],
    queryFn: () => api.analyses.events(analysisId),
    enabled: Boolean(analysisId),
    refetchInterval: terminalStatuses.includes(progress.data?.status ?? "") ? false : 1500,
  });
  const cancel = useMutation({
    mutationFn: () => api.analyses.cancel(analysisId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["analysis", analysisId] });
    },
  });

  if (analysis.isLoading || progress.isLoading)
    return <LoadingState label="Connecting to the analysis pipeline…" />;
  if (analysis.isError)
    return <ErrorState error={analysis.error} retry={() => void analysis.refetch()} />;
  if (progress.isError)
    return (
      <ErrorState
        error={progress.error}
        retry={() => void progress.refetch()}
        title="Pipeline status is unavailable"
      />
    );
  if (!analysis.data || !progress.data) return null;

  const value = progress.data.progress <= 1 ? progress.data.progress * 100 : progress.data.progress;
  const active = !terminalStatuses.includes(progress.data.status);
  const supplied = new Map(
    (progress.data.stages ?? []).map((stage) => [stage.name.toUpperCase(), stage]),
  );
  const stages = pipelineStages.map((name) => {
    const found = supplied.get(name);
    if (found) return found;
    const currentIndex = pipelineStages.indexOf(progress.data.current_stage?.toUpperCase() ?? "");
    const index = pipelineStages.indexOf(name);
    return {
      name,
      status:
        currentIndex < 0
          ? "pending"
          : index < currentIndex
            ? "completed"
            : index === currentIndex
              ? "running"
              : "pending",
    };
  });

  return (
    <div className="page-stack progress-page">
      <PageHeader
        eyebrow={`Analysis ${analysisId.slice(0, 12)}`}
        title={
          active
            ? "Collecting acceptance evidence"
            : progress.data.status === "completed"
              ? "Evidence collection complete"
              : `Analysis ${progress.data.status}`
        }
        description={
          active
            ? "Each stage emits structured progress and preserves its timing."
            : progress.data.error_summary || "The pipeline reached a terminal state."
        }
        actions={
          active ? (
            <Button variant="danger" loading={cancel.isPending} onClick={() => cancel.mutate()}>
              <Square size={14} /> Cancel run
            </Button>
          ) : (
            <Button onClick={() => void navigate(`/analyses/${analysisId}`)}>
              Open results <ExternalLink size={15} />
            </Button>
          )
        }
      />

      <Card className={cx("progress-hero", `progress-hero--${progress.data.status}`)}>
        <div className="progress-orbit">
          <span>
            {Math.round(value)}
            <small>%</small>
          </span>
        </div>
        <div className="progress-hero__content">
          <div>
            <StatusBadge status={progress.data.status} />
            <span className="live-label">
              {active ? (
                <>
                  <i /> Live
                </>
              ) : (
                "Final"
              )}
            </span>
          </div>
          <h2>
            {progress.data.current_stage
              ? titleCase(progress.data.current_stage)
              : titleCase(progress.data.status)}
          </h2>
          <ProgressBar value={value} label="Pipeline completion" />
          <p>
            {active
              ? "You can leave this page; analysis continues through the configured task backend."
              : progress.data.status === "completed"
                ? "The verdict, risk components, policy decisions, and portable bundle are ready."
                : "Review the error below, then adjust the source or validation plan before retrying."}
          </p>
        </div>
      </Card>

      {cancel.error ? (
        <div className="form-error" role="alert">
          {cancel.error.message}
        </div>
      ) : null}
      {progress.data.error_summary ? (
        <Card className="failure-panel">
          <AlertTriangle size={21} />
          <div>
            <h2>Analysis could not continue</h2>
            <p>{progress.data.error_summary}</p>
            <Link className="text-link" to={`/analyses/new?project=${analysis.data.project_id}`}>
              <RotateCcw size={15} /> Create a revised run
            </Link>
          </div>
        </Card>
      ) : null}

      <div className="progress-layout">
        <Card className="stage-card">
          <div className="section-heading">
            <div>
              <h2>Pipeline stages</h2>
              <p>Deterministic, isolated, and observable</p>
            </div>
          </div>
          <ol className="stage-list">
            {stages.map((stage) => (
              <li
                key={stage.name}
                className={cx(
                  `stage--${stage.status}`,
                  progress.data.current_stage?.toUpperCase() === stage.name && "stage--current",
                )}
              >
                <span className="stage-icon">
                  {stage.status === "completed" ? (
                    <Check size={14} />
                  ) : stage.status === "failed" ? (
                    <X size={14} />
                  ) : stage.status === "running" ? (
                    <span className="stage-pulse" />
                  ) : (
                    <Circle size={10} />
                  )}
                </span>
                <div>
                  <strong>{titleCase(stage.name)}</strong>
                  {stage.message ? <small>{stage.message}</small> : null}
                </div>
                <span className="stage-time">
                  {stage.duration_ms
                    ? formatDuration(stage.duration_ms)
                    : stage.status === "running"
                      ? "Running"
                      : ""}
                </span>
              </li>
            ))}
          </ol>
        </Card>

        <Card className="events-card">
          <div className="section-heading">
            <div>
              <h2>Structured events</h2>
              <p>Newest pipeline signals</p>
            </div>
            {events.isFetching ? (
              <span className="live-label">
                <i /> Updating
              </span>
            ) : null}
          </div>
          <div className="event-stream" aria-live="polite">
            {events.data?.items
              .slice()
              .reverse()
              .map((event, index) => (
                <article key={event.id ?? `${event.timestamp}-${index}`}>
                  <span className={cx("event-level", `event-level--${event.level ?? "info"}`)} />
                  <div>
                    <div>
                      <strong>{event.stage ? titleCase(event.stage) : "Analysis"}</strong>
                      <time>{formatDate(event.created_at ?? event.timestamp)}</time>
                    </div>
                    <p>{event.message}</p>
                    {event.duration_ms ? (
                      <small>
                        <Clock3 size={12} /> {formatDuration(event.duration_ms)}
                      </small>
                    ) : null}
                  </div>
                </article>
              ))}
            {!events.data?.items.length ? (
              <div className="event-empty">
                <Clock3 size={19} />
                <p>Waiting for the first structured event…</p>
              </div>
            ) : null}
          </div>
        </Card>
      </div>
    </div>
  );
}
