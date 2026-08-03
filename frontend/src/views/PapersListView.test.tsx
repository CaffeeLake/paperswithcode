import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";
import PapersListView from "@/views/PapersListView";

let infiniteState: Record<string, unknown>;
const paperParams = vi.fn();

vi.mock("@/hooks/usePapers", () => ({
  useInfinitePapers: (params: unknown) => {
    paperParams(params);
    return infiniteState;
  },
}));

vi.mock("@/hooks/useDebounce", () => ({ useDebounce: (value: string) => value }));
vi.mock("@/hooks/useIntersectionObserver", () => ({
  useIntersectionObserver: () => ({ targetRef: { current: null }, isIntersecting: false }),
}));
vi.mock("@tanstack/react-query", () => ({
  useQuery: () => ({ data: [] }),
}));
vi.mock("@/components", () => ({
  Icon: () => <span />,
  PaperCard: () => <article />,
}));

const Location = () => <div data-testid="location">{useLocation().search}</div>;

const renderView = (entry: string) => render(
  <MemoryRouter initialEntries={[entry]}>
    <Routes>
      <Route path="/papers" element={<><PapersListView /><Location /></>} />
    </Routes>
  </MemoryRouter>,
);

describe("PapersListView repository scopes", () => {
  beforeEach(() => {
    paperParams.mockClear();
    infiniteState = {
      data: {
        pages: [{
          count: 3,
          results: [],
          next_page: null,
          previous_page: null,
          scope: {
            kind: "framework",
            framework_slug: "lerobot",
            framework_name: "LeRobot",
            repository: "huggingface/lerobot",
            github_url: "https://github.com/huggingface/lerobot",
            introducing_paper_arxiv_id: "2602.22818",
          },
        }],
      },
      error: null,
      isLoading: false,
      hasNextPage: false,
      isFetchingNextPage: false,
      fetchNextPage: vi.fn(),
    };
  });

  it("forwards URL filters and shows framework resources without the generic sidebar", () => {
    renderView("/papers?framework=lerobot&search=robot&order_by=citation_count&time=week&has_hf_artifacts=true");

    expect(paperParams).toHaveBeenLastCalledWith(expect.objectContaining({
      framework: "lerobot",
      repository: undefined,
      search: "robot",
      order_by: "citation_count",
      time: "week",
      has_hf_artifacts: true,
    }));
    expect(screen.getByRole("heading", { name: /Papers implemented by LeRobot/ })).toBeInTheDocument();
    expect(screen.getByText(/GitHub repository/)).toHaveTextContent("huggingface/lerobot");
    expect(screen.queryByRole("button", { name: "Has code" })).toBeNull();
    expect(screen.getByRole("button", { name: "Has artifacts" })).toBeInTheDocument();
    expect(screen.queryByText("Top Domains")).toBeNull();
    expect(screen.getByRole("link", { name: "GitHub" })).toHaveAttribute(
      "href",
      "https://github.com/huggingface/lerobot",
    );
    expect(screen.getByRole("link", { name: "Introducing paper" })).toHaveAttribute(
      "href",
      "/paper/2602.22818",
    );
  });

  it("preserves framework scope when sort, time, artifact, and search controls change", async () => {
    renderView("/papers?framework=lerobot");

    fireEvent.click(screen.getByRole("button", { name: "newest" }));
    expect(screen.getByTestId("location")).toHaveTextContent("framework=lerobot");
    expect(screen.getByTestId("location")).toHaveTextContent("order_by=date_published");

    fireEvent.click(screen.getByRole("button", { name: "This Month" }));
    fireEvent.click(screen.getByRole("button", { name: "Has artifacts" }));
    fireEvent.change(screen.getByPlaceholderText("Search title or abstract…"), {
      target: { value: "vision" },
    });

    await waitFor(() => {
      const location = screen.getByTestId("location").textContent || "";
      expect(location).toContain("framework=lerobot");
      expect(location).toContain("time=month");
      expect(location).toContain("has_hf_artifacts=true");
      expect(location).toContain("search=vision");
    });
  });

  it("shows a framework-not-found state for a 404", () => {
    infiniteState = {
      ...infiniteState,
      data: undefined,
      error: new ApiError(new Response("{}", { status: 404, statusText: "Not Found" }), "{}"),
    };

    renderView("/papers?framework=missing");

    expect(screen.getByText("Framework not found.")).toBeInTheDocument();
    expect(screen.queryByText("Failed to load papers. Please try again.")).toBeNull();
  });

  it("keeps the code toggle on the unfiltered papers page", () => {
    infiniteState = {
      ...infiniteState,
      data: { pages: [{ count: 0, results: [], next_page: null, previous_page: null }] },
    };

    renderView("/papers");

    expect(screen.getByRole("button", { name: "Has code" })).toBeInTheDocument();
  });
});
