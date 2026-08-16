import { useMemo, useState } from "react";
import { Check, CheckCircle, ClipboardText, Eye } from "@phosphor-icons/react";
import { useOperations } from "../app/useOperations";
import type { InspectionTask, TaskStatus } from "../api/types";
import { Button, EmptyBlock, Panel, ResourceState, StatusBadge } from "../components/ui";
import { formatDateTime } from "../lib/format";

function TaskRecord({
  task,
  busy,
  onAction,
}: {
  task: InspectionTask;
  busy?: string;
  onAction: (task: InspectionTask, action: "acknowledge" | "resolve") => void;
}) {
  return (
    <Panel as="article" className={`task-record task-record--${task.priority.toLowerCase()}`}>
      <div className="task-record__heading">
        <div>
          <StatusBadge status={task.priority} />
          <StatusBadge status={task.status} />
        </div>
        <code>{task.id}</code>
      </div>
      <h2>{task.title}</h2>
      {task.deviceCode ? <strong className="task-device">{task.deviceCode}</strong> : null}
      <p>{task.reason}</p>
      {task.instructions ? <div className="task-instructions"><ClipboardText size={18} aria-hidden="true" /><span>{task.instructions}</span></div> : null}
      {task.evidenceRefs.length > 0 ? <p className="record-refs">Evidence: {task.evidenceRefs.join(", ")}</p> : null}
      <span className="task-time">Tạo lúc {formatDateTime(task.createdAt)}</span>
      <div className="task-actions">
        {task.status === "unread" ? (
          <Button variant="secondary" busy={busy === `${task.id}:acknowledge`} onClick={() => onAction(task, "acknowledge")}>
            <Eye size={17} aria-hidden="true" /> Xác nhận đã đọc
          </Button>
        ) : null}
        {task.status === "acknowledged" ? (
          <Button busy={busy === `${task.id}:resolve`} onClick={() => onAction(task, "resolve")}>
            <Check size={17} aria-hidden="true" /> Đánh dấu đã xử lý
          </Button>
        ) : <span className="resolved-label"><CheckCircle size={18} weight="fill" aria-hidden="true" /> Nhiệm vụ đã đóng</span>}
      </div>
    </Panel>
  );
}

export function TasksPage() {
  const { api, tasks } = useOperations();
  const [filter, setFilter] = useState<TaskStatus | "all">("all");
  const [busy, setBusy] = useState<string>();
  const [actionError, setActionError] = useState<string>();
  const visibleTasks = useMemo(() => {
    const all = tasks.data ?? [];
    return filter === "all" ? all : all.filter((task) => task.status === filter);
  }, [filter, tasks.data]);

  const updateTask = async (task: InspectionTask, action: "acknowledge" | "resolve") => {
    setBusy(`${task.id}:${action}`);
    setActionError(undefined);
    try {
      await api.updateTask(task, action);
      tasks.refresh();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Không cập nhật được nhiệm vụ.");
    } finally {
      setBusy(undefined);
    }
  };

  const count = (status: TaskStatus) => (tasks.data ?? []).filter((task) => task.status === status).length;
  return (
    <div className="page-stack">
      <header className="page-heading">
        <div><p className="context-label">Inspection Tasks</p><h1>Nhiệm vụ hiện trường</h1><p>Evidence chưa đủ được chuyển thành việc kiểm tra có thể xác nhận và đóng.</p></div>
        <div className="page-heading__status"><StatusBadge status={count("unread") > 0 ? "HIGH" : "RESOLVED"} label={`${count("unread")} chưa đọc`} /></div>
      </header>
      <div className="segmented-control" role="group" aria-label="Lọc nhiệm vụ">
        {(["all", "unread", "acknowledged", "resolved"] as const).map((status) => (
          <button key={status} aria-pressed={filter === status} onClick={() => setFilter(status)}>
            {status === "all" ? `Tất cả ${(tasks.data ?? []).length}` : `${status} ${count(status)}`}
          </button>
        ))}
      </div>
      {actionError ? <p className="form-error" role="alert">{actionError}</p> : null}
      <ResourceState status={tasks.status} error={tasks.error} hasData={Boolean(tasks.data)} onRetry={tasks.refresh}>
        {visibleTasks.length === 0 ? <EmptyBlock message="Không có nhiệm vụ trong bộ lọc này." /> : (
          <div className="task-grid">
            {visibleTasks.map((task) => <TaskRecord key={task.id} task={task} busy={busy} onAction={(item, action) => void updateTask(item, action)} />)}
          </div>
        )}
      </ResourceState>
    </div>
  );
}
