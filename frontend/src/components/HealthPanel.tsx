import { ChartLine, ClockCountdown, Database, HardDrives, Pulse } from "@phosphor-icons/react";
import type { HealthStatus } from "../api/types";
import { formatDuration, formatNumber, formatPercent } from "../lib/format";
import { Metric, Panel, StatusBadge } from "./ui";

export function HealthPanel({ health }: { health: HealthStatus }) {
  return (
    <Panel
      title="Sức khỏe pipeline"
      description="Tín hiệu ingest và lưu trữ do API quan sát được."
      action={<StatusBadge status={health.status} />}
    >
      <dl className="health-grid">
        <Metric label="Chu kỳ batch" value={formatDuration(health.batchPeriodSeconds)} detail={<Pulse size={16} aria-hidden="true" />} />
        <Metric label="Tỷ lệ trễ" value={formatPercent(health.lateRatio)} detail={<ChartLine size={16} aria-hidden="true" />} />
        <Metric label="Clock skew" value={formatNumber(health.clockSkewSeconds, " giây")} detail={<ClockCountdown size={16} aria-hidden="true" />} />
        <Metric label="Uptime" value={formatDuration(health.uptimeSeconds)} detail={<HardDrives size={16} aria-hidden="true" />} />
        <Metric label="Outbox depth" value={formatNumber(health.outboxDepth)} detail={<Database size={16} aria-hidden="true" />} />
        <Metric label="DB write latency" value={formatNumber(health.dbWriteLatencyMs, " ms")} />
      </dl>
      {health.missingDevices.length > 0 ? (
        <div className="health-warning" role="status">
          <strong>Thiết bị vắng mặt</strong>
          <span>{health.missingDevices.join(", ")}</span>
        </div>
      ) : null}
      {health.reasons.length > 0 ? (
        <ul className="compact-list">{health.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
      ) : null}
    </Panel>
  );
}
