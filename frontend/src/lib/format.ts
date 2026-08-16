export function formatDateTime(value?: string): string {
  if (!value) return "Chưa có thời gian";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

export function formatClockTime(value?: string | Date): string {
  if (!value) return "";
  const date = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("vi-VN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(date);
}

export function formatDuration(seconds?: number): string {
  if (seconds === undefined) return "Chưa có dữ liệu";
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)} giây`;
  if (seconds < 3_600) return `${Math.floor(seconds / 60)} phút ${Math.round(seconds % 60)} giây`;
  return `${Math.floor(seconds / 3_600)} giờ ${Math.floor((seconds % 3_600) / 60)} phút`;
}

export function formatPercent(value?: number): string {
  if (value === undefined) return "Chưa có dữ liệu";
  const normalized = value <= 1 ? value * 100 : value;
  return `${normalized.toFixed(normalized < 10 ? 1 : 0)}%`;
}

export function formatNumber(value?: number, suffix = ""): string {
  if (value === undefined) return "Chưa có dữ liệu";
  return `${value.toLocaleString("vi-VN", { maximumFractionDigits: 2 })}${suffix}`;
}

export function humanize(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}
