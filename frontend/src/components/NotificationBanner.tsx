import { BellRinging } from "@phosphor-icons/react";
import { Link } from "react-router-dom";
import type { InspectionTask } from "../api/types";
import { StatusBadge } from "./ui";

export function NotificationBanner({ tasks }: { tasks: InspectionTask[] }) {
  const urgent = tasks
    .filter((task) => task.status === "unread" && (task.priority === "HIGH" || task.priority === "CRITICAL"))
    .sort((a, b) => (a.priority === "CRITICAL" ? -1 : b.priority === "CRITICAL" ? 1 : 0));
  const task = urgent[0];
  if (!task) return null;

  return (
    <aside className={`priority-banner priority-banner--${task.priority.toLowerCase()}`} role="alert">
      <BellRinging size={22} weight="fill" aria-hidden="true" />
      <div>
        <span><StatusBadge status={task.priority} /> {urgent.length > 1 ? `và ${urgent.length - 1} cảnh báo khác` : ""}</span>
        <strong>{task.title}</strong>
        <p>{task.deviceCode ? `${task.deviceCode}: ` : ""}{task.reason}</p>
      </div>
      <Link className="button button--secondary" to="/inspection-tasks">Xem nhiệm vụ</Link>
    </aside>
  );
}
