import { useMemo, useState } from "react";
import type { MetricHistoryPoint } from "../hooks/useMetricHistory";
import { formatClockTime, formatNumber } from "../lib/format";
import { Panel } from "./ui";

export interface ChartSeries {
  id: string;
  label: string;
  /** CSS custom property name, e.g. "--series-1". */
  colorVar: string;
  unit?: string;
}

const WIDTH = 640;
const HEIGHT = 200;
const PAD = { top: 12, right: 16, bottom: 24, left: 8 };
const PLOT_WIDTH = WIDTH - PAD.left - PAD.right;
const PLOT_HEIGHT = HEIGHT - PAD.top - PAD.bottom;

function niceDomain(values: number[], explicit?: [number, number]): [number, number] {
  if (explicit) return explicit;
  if (values.length === 0) return [0, 1];
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (min === max) return [min - 1, max + 1];
  const pad = (max - min) * 0.1;
  return [min - pad, max + pad];
}

/**
 * Live trailing line chart over a client-side rolling buffer (see
 * useMetricHistory) — mark spec: 2px lines, round caps, a filled data-end +
 * direct label on the latest point per series, crosshair+tooltip hover,
 * legend for 2+ series (a single series is named by the panel title
 * instead, per dataviz skill's "no legend box for one series").
 */
export function LiveMetricChart({
  title,
  description,
  points,
  series,
  yDomain,
}: {
  title: string;
  description?: string;
  points: MetricHistoryPoint[];
  series: ChartSeries[];
  yDomain?: [number, number];
}) {
  const [hoverIndex, setHoverIndex] = useState<number>();

  const { xScale, yScale, paths, latest, yTicks } = useMemo(() => {
    const times = points.map((point) => point.t);
    const minT = times.length ? Math.min(...times) : 0;
    const maxT = times.length ? Math.max(...times) : 1;
    const span = Math.max(maxT - minT, 1);
    const xScaleFn = (t: number) => PAD.left + ((t - minT) / span) * PLOT_WIDTH;

    const allValues = points.flatMap((point) => series.map((serie) => point.values[serie.id]).filter((v): v is number => v !== undefined));
    const [yMin, yMax] = niceDomain(allValues, yDomain);
    const ySpan = Math.max(yMax - yMin, 1e-9);
    const yScaleFn = (value: number) => PAD.top + PLOT_HEIGHT - ((value - yMin) / ySpan) * PLOT_HEIGHT;

    const pathsBySeries = series.map((serie) => {
      const coords = points
        .map((point) => (point.values[serie.id] !== undefined ? [xScaleFn(point.t), yScaleFn(point.values[serie.id])] : undefined))
        .filter((coord): coord is [number, number] => coord !== undefined);
      return { serie, d: coords.map(([x, y], index) => `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" "), last: coords.at(-1) };
    });

    const latestValues = series.map((serie) => ({ serie, value: points.at(-1)?.values[serie.id] }));

    const tickCount = 3;
    const ticks = Array.from({ length: tickCount + 1 }, (_, index) => yMin + (ySpan * index) / tickCount);

    return { xScale: xScaleFn, yScale: yScaleFn, paths: pathsBySeries, latest: latestValues, yTicks: ticks };
  }, [points, series, yDomain]);

  const hovered = hoverIndex !== undefined ? points[hoverIndex] : undefined;

  const onMove = (event: React.MouseEvent<SVGRectElement>) => {
    if (points.length === 0) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const ratio = (event.clientX - rect.left) / rect.width;
    const index = Math.round(ratio * (points.length - 1));
    setHoverIndex(Math.max(0, Math.min(points.length - 1, index)));
  };

  return (
    <Panel
      className="live-chart"
      title={title}
      description={description}
      action={
        series.length > 1 ? (
          <ul className="live-chart__legend">
            {series.map((serie) => (
              <li key={serie.id}>
                <i style={{ background: `var(${serie.colorVar})` }} aria-hidden="true" />
                {serie.label}
              </li>
            ))}
          </ul>
        ) : undefined
      }
    >
      {points.length < 2 ? (
        <p className="live-chart__warmup">Đang thu thập dữ liệu realtime — cần thêm vài lần cập nhật để vẽ đường xu hướng.</p>
      ) : (
        <div className="live-chart__body">
          <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="live-chart__svg" role="img" aria-label={title}>
            {yTicks.map((tick) => (
              <line
                key={tick}
                x1={PAD.left}
                x2={WIDTH - PAD.right}
                y1={yScale(tick)}
                y2={yScale(tick)}
                className="live-chart__grid"
              />
            ))}
            {paths.map(({ serie, d, last }) => (
              <g key={serie.id}>
                <path d={d} fill="none" stroke={`var(${serie.colorVar})`} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
                {last ? <circle cx={last[0]} cy={last[1]} r={3.5} fill={`var(${serie.colorVar})`} /> : null}
              </g>
            ))}
            {hovered ? (
              <line x1={xScale(hovered.t)} x2={xScale(hovered.t)} y1={PAD.top} y2={HEIGHT - PAD.bottom} className="live-chart__crosshair" />
            ) : null}
            <rect
              x={PAD.left}
              y={PAD.top}
              width={PLOT_WIDTH}
              height={PLOT_HEIGHT}
              fill="transparent"
              onMouseMove={onMove}
              onMouseLeave={() => setHoverIndex(undefined)}
            />
          </svg>
          <div className="live-chart__readout">
            {(hovered ? series.map((serie) => ({ serie, value: hovered.values[serie.id] })) : latest).map(({ serie, value }) => (
              <div key={serie.id} className="live-chart__readout-item">
                <i style={{ background: `var(${serie.colorVar})` }} aria-hidden="true" />
                <span>{serie.label}</span>
                <strong>{value === undefined ? "—" : formatNumber(value, serie.unit ? ` ${serie.unit}` : "")}</strong>
              </div>
            ))}
            <span className="live-chart__readout-time">{hovered ? formatClockTime(new Date(hovered.t)) : "hiện tại"}</span>
          </div>
        </div>
      )}
    </Panel>
  );
}
