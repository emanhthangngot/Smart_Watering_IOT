import { useEffect, useRef, useState } from "react";
import type { FarmState } from "../api/types";

export interface MetricSeriesSpec {
  id: string;
  label: string;
  deviceCode: string;
  /** Lowercase metric names to match against MetricReading.name (registry uses snake_case). */
  metricNames: string[];
}

export interface MetricHistoryPoint {
  t: number;
  values: Record<string, number>;
}

/**
 * Rolling client-side buffer of real World State snapshots, keyed by series.
 * There is no backend history endpoint (store/read_model.py only exposes the
 * latest snapshot) — each accepted `farmState` poll tick appends one real
 * point per series that has a numeric reading, capped at `maxPoints`. No
 * value is invented: series with no matching device/metric in a given
 * snapshot are simply absent from that point.
 */
export function useMetricHistory(
  state: FarmState | undefined,
  specs: MetricSeriesSpec[],
  maxPoints = 60,
): MetricHistoryPoint[] {
  const [history, setHistory] = useState<MetricHistoryPoint[]>([]);
  const specsRef = useRef(specs);
  specsRef.current = specs;

  useEffect(() => {
    if (!state) return;
    const values: Record<string, number> = {};
    for (const spec of specsRef.current) {
      const device = state.devices.find(
        (candidate) => candidate.deviceCode.toUpperCase() === spec.deviceCode.toUpperCase(),
      );
      const reading = device?.metrics.find((metric) => spec.metricNames.includes(metric.name.toLowerCase()));
      if (reading && typeof reading.value === "number" && Number.isFinite(reading.value)) {
        values[spec.id] = reading.value;
      }
    }
    if (Object.keys(values).length === 0) return;
    setHistory((current) => {
      const next = [...current, { t: Date.now(), values }];
      return next.length > maxPoints ? next.slice(next.length - maxPoints) : next;
    });
  }, [state, maxPoints]);

  return history;
}
