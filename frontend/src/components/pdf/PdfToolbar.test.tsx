import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { PdfToolbar } from "./PdfToolbar";

describe("PdfToolbar", () => {
  it("supports page, zoom, search, and original controls", () => {
    const onPage = vi.fn();
    const onToggleSearch = vi.fn();
    render(<MemoryRouter><PdfToolbar
        paperTitle="Example Paper"
        paperHref="/paper/2501.00001"
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
        onToggleSearch={onToggleSearch}
        onSearchQuery={vi.fn()}
        onSearch={vi.fn()}
      /></MemoryRouter>);

    expect(screen.getByRole("link", { name: "Example Paper — open paper page" }))
      .toHaveAttribute("href", "/paper/2501.00001");
    expect(screen.queryByText(/arXiv:/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Previous page" }));
    expect(onPage).toHaveBeenCalledWith(2);
    expect(screen.queryByRole("button", { name: "Fit width" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(onToggleSearch).toHaveBeenCalledOnce();
    expect(screen.getByRole("link", { name: "Open original" })).toHaveAttribute(
      "href", "https://arxiv.org/pdf/2501.00001",
    );
  });
});
