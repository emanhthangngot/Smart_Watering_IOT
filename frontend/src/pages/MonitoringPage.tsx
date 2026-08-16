import { useCallback } from "react";
import { useOperations } from "../app/useOperations";
import { HealthPanel } from "../components/HealthPanel";
import { LiveMetricChart } from "../components/LiveMetricChart";
import { EmptyBlock, ResourceState } from "../components/ui";
import { usePollingResource } from "../hooks/usePollingResource";
import { useMetricHistory } from "../hooks/useMetricHistory";
import type { FarmState } from "../api/types";

// Real MQTT batches land every ~0.5–5s depending on source (see api/health).
// The rest of the app polls World State every 5s (OperationsProvider), which
// is fine for status tiles but reads as choppy steps on a line chart. This
// page only needs a faster tail of the SAME real endpoint while it's
// mounted — not a new data source, just a shorter interval — so charts read
// as continuously moving instead of a stepped update every 5s.
const CHART_POLL_MS = 1_000;
const CHART_MAX_POINTS = 180; // ~3 min tail at 1s cadence

const IRRIGATION_SERIES = [
  { id: "soilMoisture", label: "SOIL_01 độ ẩm đất", deviceCode: "SOIL_01", metricNames: ["soil_moisture"], colorVar: "--series-1", unit: "%" },
  { id: "tankLevel", label: "TANK_01 mực nước", deviceCode: "TANK_01", metricNames: ["level"], colorVar: "--series-2", unit: "%" },
];

const FLOW_SERIES = [
  { id: "pumpFlow", label: "PUMP_01 lưu lượng", deviceCode: "PUMP_01", metricNames: ["flow_rate"], colorVar: "--series-1", unit: "L/min" },
];

export function MonitoringPage() {
  const { api, health } = useOperations();
  const loadFarmState = useCallback((signal: AbortSignal) => api.getFarmState(signal), [api]);
  const liveFarmState = usePollingResource<FarmState>(loadFarmState, CHART_POLL_MS);
  const irrigationHistory = useMetricHistory(liveFarmState.data, IRRIGATION_SERIES, CHART_MAX_POINTS);
  const flowHistory = useMetricHistory(liveFarmState.data, FLOW_SERIES, CHART_MAX_POINTS);

  return (
    <div className="page-stack">
      <header className="page-heading">
        <div>
          <p className="context-label">Giám sát / Diagnostics</p>
          <h1>Sức khỏe hạ tầng & xu hướng realtime</h1>
          <p>Đường xu hướng cập nhật mỗi {CHART_POLL_MS / 1000}s trực tiếp từ World State — chạy liên tục khi trang còn mở.</p>
        </div>
      </header>

      <div className="monitoring-chart-grid">
        <LiveMetricChart
          title="Xu hướng tưới"
          description="Độ ẩm đất so với mực nước tank, theo thời gian thực."
          points={irrigationHistory}
          series={IRRIGATION_SERIES}
          yDomain={[0, 100]}
        />
        <LiveMetricChart
          title="Lưu lượng bơm"
          description="PUMP_01.flow_rate — phát hiện bơm chạy nhưng không hiệu quả."
          points={flowHistory}
          series={FLOW_SERIES}
        />
      </div>

      <ResourceState status={health.status} error={health.error} hasData={Boolean(health.data)} onRetry={health.refresh}>
        {health.data ? <HealthPanel health={health.data} /> : <EmptyBlock message="Health API chưa trả dữ liệu." />}
      </ResourceState>
    </div>
  );
}
