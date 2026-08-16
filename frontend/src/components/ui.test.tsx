import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ResourceState } from "./ui";

describe("ResourceState", () => {
  it("shows loading instead of rendering premature empty content", () => {
    render(<ResourceState status="loading"><span>Không nên hiện</span></ResourceState>);
    expect(screen.getByLabelText("Đang tải dữ liệu vận hành")).toBeInTheDocument();
    expect(screen.queryByText("Không nên hiện")).not.toBeInTheDocument();
  });

  it("shows a blocking error when no last-good payload exists", () => {
    render(<ResourceState status="error" error={new Error("API down")} onRetry={vi.fn()} />);
    expect(screen.getByRole("alert")).toHaveTextContent("API down");
  });

  it("keeps last-good content and adds a non-blocking refresh error", () => {
    render(
      <ResourceState status="error" error={new Error("Refresh failed")} hasData>
        <span>Last good payload</span>
      </ResourceState>,
    );
    expect(screen.getByText("Last good payload")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Refresh failed");
  });
});
