import type { PlanDetail } from "../api/types";

const APPROVAL_STATES = new Set(["PROPOSED"]);

export interface TierOutcomeNotice {
  tone: "fast" | "restricted";
  message: string;
}

/**
 * DCS/tier only reads as three flat options in the UI (AUTO/PROPOSE/INVESTIGATE),
 * but AUTO and INVESTIGATE both skip the "operator reads plan, then reacts" pace
 * PROPOSE assumes: AUTO can execute without a decision step, INVESTIGATE silently
 * downgrades the approved action to an inspection task (tools/downgrade.py) —
 * from the operator's view the plan just jumps to NEEDS_REPLAN right after
 * approval, with no irrigation ever running. Surface that consequence before
 * the decision, not after. PROPOSE is the pace the approval UI already assumes,
 * so it gets no extra banner.
 */
export function describeTierOutcome(tier: string | undefined): TierOutcomeNotice | undefined {
  switch (tier) {
    case "AUTO":
      return {
        tone: "fast",
        message:
          "Tier AUTO: hệ thống đủ tin cậy để tự hành động, có thể thực thi ngay không chờ thao tác thêm. Theo dõi Trace nếu muốn bắt kịp diễn biến.",
      };
    case "INVESTIGATE":
      return {
        tone: "restricted",
        message:
          "Tier INVESTIGATE: DCS quá thấp để tưới. Phê duyệt sẽ KHÔNG chạy lịch tưới — tool layer tự hạ cấp thành inspection task, plan chuyển thẳng sang NEEDS_REPLAN. Xử lý nhiệm vụ kiểm tra trước khi thử lại.",
      };
    default:
      return undefined;
  }
}

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
