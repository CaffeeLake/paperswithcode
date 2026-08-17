import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PdfToolbar } from "./PdfToolbar";

describe("PdfToolbar", () => {
  it("supports page, fit-width, search, and original controls", () => {
    const onPage = vi.fn();
    const onFitWidth = vi.fn();
    const onToggleSearch = vi.fn();
    render(<PdfToolbar
      page={3}
      pages={12}
      zoomPercent={125}
      searchOpen={false}
      searchQuery=""
      searchMatch={0}
      searchCount={0}
      searching={false}
      originalUrl="https://arxiv.org/pdf/2501.00001"
      onPage={onPage}
      onZoomIn={vi.fn()}
      onZoomOut={vi.fn()}
      onFitWidth={onFitWidth}
      onToggleSearch={onToggleSearch}
      onSearchQuery={vi.fn()}
      onSearch={vi.fn()}
    />);

    fireEvent.click(screen.getByRole("button", { name: "Previous page" }));
    expect(onPage).toHaveBeenCalledWith(2);
    fireEvent.click(screen.getByRole("button", { name: "Fit width" }));
    expect(onFitWidth).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(onToggleSearch).toHaveBeenCalledOnce();
    expect(screen.getByRole("link", { name: "Open original" })).toHaveAttribute(
      "href", "https://arxiv.org/pdf/2501.00001",
    );
  });
});
