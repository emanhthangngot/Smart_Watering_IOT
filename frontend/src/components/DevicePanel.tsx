import { Cpu, Database, Timer } from "@phosphor-icons/react";
import type { DeviceSnapshot, TrustVerdict } from "../api/types";
import { formatDateTime, formatDuration, formatNumber, humanize } from "../lib/format";
import { Panel, StatusBadge } from "./ui";

export function DevicePanel({ device, trust }: { device: DeviceSnapshot; trust?: TrustVerdict }) {
  const reasons = [...new Set([...device.reasons, ...(trust?.reasons ?? [])])];
  const tier = trust?.tier ?? device.tier ?? "UNKNOWN";
  const dcs = trust?.dcs ?? device.dcs;

  return (
    <Panel className="device-panel" as="article">
      <div className="device-panel__topline">
        <div>
          <span className="device-panel__icon" aria-hidden="true"><Cpu size={20} /></span>
          <h3>{device.deviceCode}</h3>
        </div>
        <StatusBadge status={device.freshness} />
      </div>

      <div className="device-panel__meta">
        <span><Database size={16} aria-hidden="true" /> Kết nối: {humanize(device.connectivity)}</span>
        <span><Timer size={16} aria-hidden="true" /> Tuổi dữ liệu: {formatDuration(device.ageSeconds)}</span>
        <span>Sự kiện: {formatDateTime(device.eventTime)}</span>
      </div>

      <dl className="device-panel__confidence">
        <div>
          <dt>DCS</dt>
          <dd className="numeric">{dcs === undefined ? "Chưa có" : formatNumber(dcs <= 1 ? dcs * 100 : dcs, "%")}</dd>
        </div>
        <div>
          <dt>Tier</dt>
          <dd><StatusBadge status={tier} /></dd>
        </div>
      </dl>

      {device.metrics.length > 0 ? (
        <div className="device-panel__metrics" aria-label={`Chỉ số ${device.deviceCode}`}>
          {device.metrics.slice(0, 6).map((metric) => (
            <div key={metric.name}>
              <span>{humanize(metric.name)}</span>
              <strong className="numeric">
                {typeof metric.value === "number" ? formatNumber(metric.value) : String(metric.value ?? "N/A")}
                {metric.unit ? ` ${metric.unit}` : ""}
              </strong>
            </div>
          ))}
        </div>
      ) : <p className="muted-copy">API chưa trả reading mới nhất cho thiết bị này.</p>}

      <div className="reason-list">
        <strong>Lý do confidence</strong>
        {reasons.length > 0 ? (
          <ul>{reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
        ) : <p>API chưa cung cấp lý do confidence.</p>}
      </div>
    </Panel>
  );
}
