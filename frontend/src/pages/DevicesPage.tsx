import { useOperations } from "../app/useOperations";
import { DevicePanel } from "../components/DevicePanel";
import { ResourceState } from "../components/ui";

export function DevicesPage() {
  const { farmState, trust } = useOperations();
  return (
    <div className="page-stack">
      <header className="page-heading">
        <div>
          <p className="context-label">Thiết bị & evidence</p>
          <h1>Telemetry không bị che khuất</h1>
          <p>Freshness, tuổi dữ liệu và DCS được hiển thị tách biệt cho từng thiết bị.</p>
        </div>
        {farmState.data?.farmStateVersion !== undefined ? <code>state #{farmState.data.farmStateVersion}</code> : null}
      </header>
      <ResourceState
        status={farmState.status}
        error={farmState.error}
        hasData={Boolean(farmState.data)}
        isEmpty={farmState.status === "success" && (farmState.data?.devices.length ?? 0) === 0}
        emptyMessage="World State chưa có thiết bị. Hãy kiểm tra MQTT ingestion."
        onRetry={farmState.refresh}
      >
        {farmState.data?.devices.length ? (
          <div className="device-grid">
            {farmState.data.devices.map((device) => (
              <DevicePanel
                key={device.deviceCode}
                device={device}
                trust={(trust.data ?? []).find((verdict) => verdict.scope.toUpperCase() === device.deviceCode.toUpperCase())}
              />
            ))}
          </div>
        ) : null}
      </ResourceState>
    </div>
  );
}
