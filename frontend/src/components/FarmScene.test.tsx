import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { FarmWorldViewModel } from "../domain/farmWorldViewModel";
import { FarmScene } from "./FarmScene";

const world: FarmWorldViewModel = {
  entities: [{ id: "AREA_A", label: "Area A", detail: "Chưa có evidence đo được", freshness: "UNKNOWN" }],
  hasActiveFlow: false,
  expectedActual: "UNKNOWN",
};

describe("FarmScene", () => {
  it("keeps the operational state available when the spatial view is unavailable", () => {
    render(<FarmScene world={world} available={false} />);
    expect(screen.getByText(/Bản đồ farm tạm không khả dụng/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Tình trạng hiện tại" })).toBeInTheDocument();
    expect(screen.getByText("Area A")).toBeInTheDocument();
  });
});
