import type { InspectionTask, TaskStatus } from "../api/types";

export type TaskAction = "acknowledge" | "resolve";

const transitions: Record<TaskStatus, Partial<Record<TaskAction, TaskStatus>>> = {
  unread: { acknowledge: "acknowledged" },
  acknowledged: { resolve: "resolved" },
  resolved: {},
};

export function canTransitionTask(status: TaskStatus, action: TaskAction): boolean {
  return transitions[status][action] !== undefined;
}

export function assertTaskTransition(task: Pick<InspectionTask, "id" | "status">, action: TaskAction): void {
  if (!canTransitionTask(task.status, action)) {
    throw new Error(`Không thể ${action} nhiệm vụ ${task.id} khi đang ở trạng thái ${task.status}.`);
  }
}
