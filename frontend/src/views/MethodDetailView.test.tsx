import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/lib/api";
import MethodDetailView from "@/views/MethodDetailView";

afterEach(() => vi.restoreAllMocks());

describe("MethodDetailView", () => {
  it("links a native source paper route", async () => {
    vi.spyOn(apiClient, "getMethod").mockResolvedValue({
      id: "1023",
      slug: "world-action-models",
      name: "World Action Models",
      full_name: "World Action Models (WAMs)",
      source_url: "/paper/2605.12090",
      source_title: "World Action Models: The Next Frontier in Embodied AI",
      introduced_year: 2026,
      paper_count: 0,
    });
    vi.spyOn(apiClient, "getMethodTrend").mockRejectedValue(new Error("not needed"));
    vi.spyOn(apiClient, "getMethodPapers").mockResolvedValue({
      count: 0,
      next_page: null,
      previous_page: null,
      results: [],
    });

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/methods/world-action-models"]}>
          <Routes>
            <Route path="/methods/:methodSlug" element={<MethodDetailView />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(
      await screen.findByRole("link", {
        name: /World Action Models: The Next Frontier in Embodied AI/,
      }),
    ).toHaveAttribute("href", "/paper/2605.12090");
    expect(document.querySelector(".method-hero-grid")).toHaveClass(
      "method-hero-grid--wide-figure",
    );
  });
});
