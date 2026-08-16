import type { ButtonHTMLAttributes, ReactNode } from "react";
import {
  CheckCircle,
  Info,
  SpinnerGap,
  Warning,
  WarningCircle,
  XCircle,
} from "@phosphor-icons/react";
import type { AsyncStatus } from "../api/types";

type Tone = "neutral" | "success" | "warning" | "danger" | "info";

function toneFromStatus(status: string): Tone {
  const value = status.toUpperCase();
  if (["PASS", "FRESH", "AUTO", "VALID", "HEALTHY", "OK", "COMPLETED", "RESOLVED"].includes(value)) return "success";
  if (["FAIL", "OFFLINE", "CRITICAL", "INVALIDATED", "FAILED", "REJECTED", "SUSPENDED"].includes(value)) return "danger";
  if (["STALE", "SUSPECT", "HIGH", "PROPOSE", "CHALLENGED", "EXPIRED", "NEEDS_REPLAN"].includes(value)) return "warning";
  if (["INCONCLUSIVE", "INVESTIGATE", "MISSING", "UNKNOWN"].includes(value)) return "info";
  return "neutral";
}

function ToneIcon({ tone }: { tone: Tone }) {
  const props = { size: 16, weight: "fill" as const, "aria-hidden": true };
  if (tone === "success") return <CheckCircle {...props} />;
  if (tone === "danger") return <XCircle {...props} />;
  if (tone === "warning") return <Warning {...props} />;
  if (tone === "info") return <Info {...props} />;
  return <WarningCircle {...props} />;
}

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  const tone = toneFromStatus(status);
  return (
    <span className={`status-badge status-badge--${tone}`}>
      <ToneIcon tone={tone} />
      {label ?? status}
    </span>
  );
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "danger" | "ghost";
  busy?: boolean;
  children: ReactNode;
}

export function Button({
  variant = "primary",
  busy = false,
  disabled,
  children,
  className = "",
  ...props
}: ButtonProps) {
  return (
    <button
      className={`button button--${variant} ${className}`}
      disabled={disabled || busy}
      aria-busy={busy}
      {...props}
    >
      {busy ? <SpinnerGap className="spin" size={18} aria-hidden="true" /> : null}
      {children}
    </button>
  );
}

export function Panel({
  title,
  description,
  action,
  children,
  className = "",
  as: Component = "section",
}: {
  title?: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  as?: "section" | "article" | "aside";
}) {
  return (
    <Component className={`panel ${className}`}>
      {title || description || action ? (
        <div className="panel__header">
          <div>
            {title ? <h2>{title}</h2> : null}
            {description ? <p>{description}</p> : null}
          </div>
          {action ? <div className="panel__action">{action}</div> : null}
        </div>
      ) : null}
      {children}
    </Component>
  );
}

export function Metric({ label, value, detail }: { label: string; value: ReactNode; detail?: ReactNode }) {
  return (
    <div className="metric">
      <dt>{label}</dt>
      <dd>{value}{detail ? <span aria-hidden="true">{detail}</span> : null}</dd>
    </div>
  );
}

export function ResourceState({
  status,
  error,
  hasData = false,
  isEmpty,
  emptyMessage = "Chưa có dữ liệu.",
  onRetry,
  children,
}: {
  status: AsyncStatus;
  error?: Error;
  hasData?: boolean;
  isEmpty?: boolean;
  emptyMessage?: string;
  onRetry?: () => void;
  children?: ReactNode;
}) {
  if (status === "idle" || status === "loading") {
    return <LoadingBlock />;
  }
  if (status === "error" && !hasData) {
    return <ErrorBlock error={error} onRetry={onRetry} />;
  }
  if (isEmpty) return <EmptyBlock message={emptyMessage} />;
  return (
    <>
      {status === "error" ? <InlineError error={error} onRetry={onRetry} /> : null}
      {children}
    </>
  );
}

export function LoadingBlock({ label = "Đang tải dữ liệu vận hành" }: { label?: string }) {
  return (
    <div className="state-block" aria-busy="true" aria-label={label}>
      <SpinnerGap className="spin" size={24} aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

export function EmptyBlock({ message }: { message: string }) {
  return (
    <div className="state-block state-block--muted">
      <Info size={22} aria-hidden="true" />
      <span>{message}</span>
    </div>
  );
}

export function ErrorBlock({ error, onRetry }: { error?: Error; onRetry?: () => void }) {
  return (
    <div className="state-block state-block--error" role="alert">
      <WarningCircle size={24} aria-hidden="true" />
      <div>
        <strong>Không tải được dữ liệu</strong>
        <p>{error?.message ?? "FarmOps API chưa sẵn sàng."}</p>
      </div>
      {onRetry ? <Button variant="secondary" onClick={onRetry}>Thử lại</Button> : null}
    </div>
  );
}

export function InlineError({ error, onRetry }: { error?: Error; onRetry?: () => void }) {
  return (
    <div className="inline-error" role="alert">
      <WarningCircle size={18} aria-hidden="true" />
      <span>{error?.message ?? "Dữ liệu mới nhất chưa tải được. Đang giữ bản gần nhất."}</span>
      {onRetry ? <button onClick={onRetry}>Thử lại</button> : null}
    </div>
  );
}
