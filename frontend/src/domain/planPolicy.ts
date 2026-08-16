import type { PlanDetail } from "../api/types";

const APPROVAL_STATES = new Set(["PROPOSED"]);

export interface PlanDecisionPolicy {
  canDecide: boolean;
  pendingApproval: boolean;
  expired: boolean;
  reason?: string;
}

export function planDecisionPolicy(plan: PlanDetail, now = new Date()): PlanDecisionPolicy {
  const expiresAt = plan.approvalExpiresAt ? new Date(plan.approvalExpiresAt) : undefined;
  const expired = Boolean(expiresAt && !Number.isNaN(expiresAt.getTime()) && expiresAt.getTime() <= now.getTime());
  if (!plan.requiresApproval) return { canDecide: false, pendingApproval: false, expired, reason: "Backend không yêu cầu approval cho revision này." };
  if (!plan.revisionHash) return { canDecide: false, pendingApproval: false, expired, reason: "Thiếu revision hash; khóa quyết định an toàn." };
  if (expired) return { canDecide: false, pendingApproval: false, expired, reason: "Cửa sổ approval đã hết hạn. Tải revision mới từ backend." };
  if (!APPROVAL_STATES.has(plan.status)) return { canDecide: false, pendingApproval: false, expired, reason: `Backend báo revision ở trạng thái ${plan.status}, không chờ quyết định.` };
  return { canDecide: true, pendingApproval: true, expired };
}
