import { useState } from "react";
import { CheckCircle, Key, WarningCircle, XCircle } from "@phosphor-icons/react";
import type { FarmOpsApi } from "../api/client";
import { isRevisionConflict } from "../api/client";
import type { PlanDetail } from "../api/types";
import { formatDateTime } from "../lib/format";
import { planDecisionPolicy } from "../domain/planPolicy";
import { Button, Panel } from "./ui";

export function PlanApproval({
  api,
  plan,
  hasOperatorToken,
  onSuccess,
}: {
  api: FarmOpsApi;
  plan: PlanDetail;
  hasOperatorToken: boolean;
  onSuccess: () => void;
}) {
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState<"approve" | "reject">();
  const [message, setMessage] = useState<{ tone: "success" | "error" | "stale"; text: string }>();
  const policy = planDecisionPolicy(plan);
  const canDecide = policy.canDecide && hasOperatorToken;

  const decide = async (decision: "approve" | "reject") => {
    setBusy(decision);
    setMessage(undefined);
    try {
      await api.decidePlan(plan.planRevisionId, decision, {
        revisionHash: plan.revisionHash,
        comment: comment.trim() || undefined,
      });
      setMessage({
        tone: "success",
        text: decision === "approve" ? "Đã phê duyệt đúng revision hiện tại." : "Đã từ chối revision hiện tại.",
      });
      onSuccess();
    } catch (error) {
      if (isRevisionConflict(error)) {
        setMessage({
          tone: "stale",
          text: "Revision hash không còn khớp. Kế hoạch đã thay đổi hoặc phê duyệt đã hết hạn. Hãy tải lại trước khi quyết định.",
        });
      } else {
        setMessage({ tone: "error", text: error instanceof Error ? error.message : "Không gửi được quyết định." });
      }
    } finally {
      setBusy(undefined);
    }
  };

  return (
    <Panel
      title="Phê duyệt của người vận hành"
      description="Quyết định luôn gắn với revision hash chính xác bên dưới."
      className="approval-panel"
    >
      <div className="revision-hash">
        <span>Revision hash</span>
        <code>{plan.revisionHash || "API chưa trả revision hash"}</code>
      </div>
      {plan.approvalExpiresAt ? <p className={policy.expired ? "approval-expired" : ""}>Hết hạn: <strong>{formatDateTime(plan.approvalExpiresAt)}</strong>{policy.expired ? " (đã hết hạn)" : ""}</p> : null}
      <label className="field">
        <span>Ghi chú quyết định</span>
        <textarea
          value={comment}
          onChange={(event) => setComment(event.target.value)}
          rows={3}
          placeholder="Nêu điều kiện hoặc lý do nếu cần"
          maxLength={500}
        />
      </label>
      {!hasOperatorToken ? (
        <p className="approval-hint"><Key size={17} aria-hidden="true" /> Cần cấu hình operator token trước khi phê duyệt.</p>
      ) : null}
      {!plan.revisionHash ? (
        <p className="approval-hint"><WarningCircle size={17} aria-hidden="true" /> Không được phê duyệt khi thiếu revision hash.</p>
      ) : null}
      {policy.reason ? <p className="approval-hint"><WarningCircle size={17} aria-hidden="true" /> {policy.reason}</p> : null}
      {message ? (
        <div className={`decision-message decision-message--${message.tone}`} role={message.tone === "success" ? "status" : "alert"}>
          {message.tone === "success" ? <CheckCircle size={20} aria-hidden="true" /> : <WarningCircle size={20} aria-hidden="true" />}
          <span>{message.text}</span>
        </div>
      ) : null}
      <div className="approval-actions">
        <Button
          variant="danger"
          disabled={!canDecide || Boolean(busy)}
          busy={busy === "reject"}
          onClick={() => void decide("reject")}
        >
          <XCircle size={18} aria-hidden="true" /> Từ chối
        </Button>
        <Button
          disabled={!canDecide || Boolean(busy)}
          busy={busy === "approve"}
          onClick={() => void decide("approve")}
        >
          <CheckCircle size={18} aria-hidden="true" /> Phê duyệt revision
        </Button>
      </div>
    </Panel>
  );
}
