import { describe, expect, it } from "vitest";
import { describeTierOutcome } from "./planPolicy";

describe("describeTierOutcome", () => {
  it("warns AUTO can execute without waiting on a decision step", () => {
    const notice = describeTierOutcome("AUTO");
    expect(notice?.tone).toBe("fast");
    expect(notice?.message).toMatch(/AUTO/);
  });

  it("warns INVESTIGATE approval will not run the irrigation action", () => {
    const notice = describeTierOutcome("INVESTIGATE");
    expect(notice?.tone).toBe("restricted");
    expect(notice?.message).toMatch(/INVESTIGATE/);
    expect(notice?.message).toMatch(/KHÔNG chạy lịch tưới/);
  });

  it("stays silent for PROPOSE — the pace the approval UI already assumes", () => {
    expect(describeTierOutcome("PROPOSE")).toBeUndefined();
  });

  it("stays silent for unknown/missing tier", () => {
    expect(describeTierOutcome(undefined)).toBeUndefined();
    expect(describeTierOutcome("UNKNOWN")).toBeUndefined();
  });
});
