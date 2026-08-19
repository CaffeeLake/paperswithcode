import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PaperSelectionCard } from "./PaperSelectionCard";

const selection = {
  routeId: "2608.09119",
  paperVersion: "v1",
  page: 4,
  text: "The selected passage is quoted evidence.",
};

describe("PaperSelectionCard", () => {
  it("shows the claimed page and exact quote without calling it verified", () => {
    render(<PaperSelectionCard selection={selection} />);
    expect(screen.getByText("Selection · Page 4")).toBeInTheDocument();
    expect(screen.getByText(selection.text)).toBeInTheDocument();
    expect(screen.queryByText(/verified/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove selected paper passage" })).not.toBeInTheDocument();
  });

  it("lets keyboard users remove a draft selection", () => {
    const onRemove = vi.fn();
    render(<PaperSelectionCard selection={selection} editable onRemove={onRemove} />);
    fireEvent.click(screen.getByRole("button", { name: "Remove selected paper passage" }));
    expect(onRemove).toHaveBeenCalledTimes(1);
  });
});
