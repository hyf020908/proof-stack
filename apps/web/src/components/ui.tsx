import { LoaderCircle, TriangleAlert, X } from "lucide-react";
import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";

export const cx = (...classes: Array<string | false | null | undefined>): string =>
  classes.filter(Boolean).join(" ");

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
  loading?: boolean;
}

export function Button({
  className,
  variant = "primary",
  size = "md",
  loading,
  disabled,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      className={cx("button", `button--${variant}`, `button--${size}`, className)}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? <LoaderCircle className="spin" aria-hidden="true" size={16} /> : null}
      {children}
    </button>
  );
}

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cx("glass-card", className)} {...props} />;
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: string }) {
  return <span className={cx("badge", `badge--${tone.toLowerCase()}`)}>{children}</span>;
}

export function VerdictBadge({ verdict }: { verdict?: string | null }) {
  const value = verdict ?? "unknown";
  return <Badge tone={value}>{value}</Badge>;
}

export function SeverityBadge({ severity }: { severity: string }) {
  return <Badge tone={severity}>{severity}</Badge>;
}

export function StatusBadge({ status }: { status: string }) {
  const tone =
    status === "completed" || status === "passed"
      ? "pass"
      : status === "failed" || status === "timed_out"
        ? "fail"
        : status === "cancelled" || status === "skipped" || status === "unavailable"
          ? "neutral"
          : "running";
  return <Badge tone={tone}>{status.replaceAll("_", " ")}</Badge>;
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
        <h1>{title}</h1>
        {description ? <p>{description}</p> : null}
      </div>
      {actions ? <div className="page-header__actions">{actions}</div> : null}
    </header>
  );
}

export function LoadingState({ label = "Loading evidence…" }: { label?: string }) {
  return (
    <div className="state-panel" role="status" aria-live="polite">
      <LoaderCircle className="spin" aria-hidden="true" />
      <p>{label}</p>
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="state-panel state-panel--empty">
      {icon ? <span className="state-panel__icon">{icon}</span> : null}
      <h2>{title}</h2>
      <p>{description}</p>
      {action}
    </div>
  );
}

export function ErrorState({
  error,
  retry,
  title = "We could not load this view",
}: {
  error: unknown;
  retry?: () => void;
  title?: string;
}) {
  const message = error instanceof Error ? error.message : "An unexpected API error occurred.";
  return (
    <div className="state-panel state-panel--error" role="alert">
      <TriangleAlert aria-hidden="true" />
      <h2>{title}</h2>
      <p>{message}</p>
      {retry ? (
        <Button variant="secondary" onClick={retry}>
          Try again
        </Button>
      ) : null}
    </div>
  );
}

export function ProgressBar({ value, label }: { value: number; label?: string }) {
  const normalized = Math.min(100, Math.max(0, Number.isFinite(value) ? value : 0));
  return (
    <div className="progress-group">
      {label ? (
        <div className="progress-label">
          <span>{label}</span>
          <span>{Math.round(normalized)}%</span>
        </div>
      ) : null}
      <div
        className="progress-track"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(normalized)}
        aria-label={label ?? "Progress"}
      >
        <span style={{ width: `${normalized}%` }} />
      </div>
    </div>
  );
}

export function Modal({
  open,
  title,
  description,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  description?: string;
  onClose: () => void;
  children: ReactNode;
}) {
  if (!open) return null;
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="modal glass-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header>
          <div>
            <h2 id="modal-title">{title}</h2>
            {description ? <p>{description}</p> : null}
          </div>
          <button className="icon-button" aria-label="Close dialog" onClick={onClose}>
            <X size={18} />
          </button>
        </header>
        {children}
      </section>
    </div>
  );
}

export function MetricCard({
  label,
  value,
  detail,
  icon,
  tone,
}: {
  label: string;
  value: string | number;
  detail?: string;
  icon?: ReactNode;
  tone?: string;
}) {
  return (
    <Card className={cx("metric-card", tone && `metric-card--${tone}`)}>
      <div className="metric-card__head">
        <span>{label}</span>
        {icon}
      </div>
      <strong>{value}</strong>
      {detail ? <small>{detail}</small> : null}
    </Card>
  );
}

export function Pagination({
  page,
  pageSize,
  total,
  onPage,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPage: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) return null;
  return (
    <nav className="pagination" aria-label="Pagination">
      <Button variant="ghost" size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        Previous
      </Button>
      <span>
        Page {page} of {pages}
      </span>
      <Button variant="ghost" size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        Next
      </Button>
    </nav>
  );
}
