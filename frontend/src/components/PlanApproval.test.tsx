import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApiError, FarmOpsApi } from "../api/client";
import type { PlanDetail } from "../api/types";
import { PlanApproval } from "./PlanApproval";

const plan: PlanDetail = {
  planLineageId: "PLAN-001",
  planRevisionId: "PLAN-001-V2",
  revisionHash: "sha256:exact-revision-hash",
  version: 2,
  status: "PROPOSED",
  goal: { type: "IRRIGATION", area: "A" },
  evidenceRefs: [],
  constraints: [],
  assumptions: [],
  actions: [],
  expectedOutcomes: [],
  waterBudget: {},
  confidence: { dcs: 0.8, tier: "PROPOSE" },
  requiresApproval: true,
  challenges: [],
  verifications: [],
};

describe("PlanApproval", () => {
  it("submits the exact revision hash", async () => {
    const user = userEvent.setup();
    const api = new FarmOpsApi("operator-token", "");
    const decide = vi.spyOn(api, "decidePlan").mockResolvedValue();
    render(<PlanApproval api={api} plan={plan} hasOperatorToken onSuccess={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /Phê duyệt revision/i }));
    expect(decide).toHaveBeenCalledWith(
      "PLAN-001-V2",
      "approve",
      { revisionHash: "sha256:exact-revision-hash", comment: undefined },
    );
  });

  it("surfaces stale hash conflicts as a required reload", async () => {
    const user = userEvent.setup();
    const api = new FarmOpsApi("operator-token", "");
    vi.spyOn(api, "decidePlan").mockRejectedValue(new ApiError("revision hash mismatch", 409, {}));
    render(<PlanApproval api={api} plan={plan} hasOperatorToken onSuccess={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /Phê duyệt revision/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Revision hash không còn khớp");
  });

  it("blocks approval when the operator token is missing", () => {
    const api = new FarmOpsApi("", "");
    render(<PlanApproval api={api} plan={plan} hasOperatorToken={false} onSuccess={vi.fn()} />);
    expect(screen.getByRole("button", { name: /Phê duyệt revision/i })).toBeDisabled();
    expect(screen.getByText(/Cần cấu hình operator token/i)).toBeInTheDocument();
  });
});
