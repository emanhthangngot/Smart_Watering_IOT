import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Verification } from "../api/types";
import { VerificationPanels } from "./VerificationPanels";

const verifications: Verification[] = [
  {
    id: "AV-1",
    layer: "ACTION",
    expected: { id: "IRR-104", status: "PENDING" },
    observed: { id: "IRR-104", status: "PENDING" },
    result: "PASS",
    evidenceRefs: ["tool-call-1"],
  },
  {
    id: "OV-1",
    layer: "OUTCOME",
    expected: "flow >= 8 L/min",
    observed: "flow = 4.5 L/min",
    result: "FAIL",
    evidenceRefs: ["r-pump-2"],
  },
  {
    id: "OV-2",
    layer: "OUTCOME",
    expected: "soil response",
    observed: null,
    result: "INCONCLUSIVE",
    evidenceRefs: [],
  },
];

describe("VerificationPanels", () => {
  it("never merges Action and Outcome verification", () => {
    render(<VerificationPanels verifications={verifications} />);
    const actionPanel = screen.getByRole("heading", { name: "Action Verification" }).closest("section");
    const outcomePanel = screen.getByRole("heading", { name: "Outcome Verification" }).closest("section");
    expect(actionPanel).not.toBeNull();
    expect(outcomePanel).not.toBeNull();
    expect(within(actionPanel!).getByText("PASS")).toBeInTheDocument();
    expect(within(actionPanel!).queryByText("FAIL")).not.toBeInTheDocument();
    expect(within(outcomePanel!).getByText("FAIL")).toBeInTheDocument();
    expect(within(outcomePanel!).getByText("INCONCLUSIVE")).toBeInTheDocument();
  });
});
