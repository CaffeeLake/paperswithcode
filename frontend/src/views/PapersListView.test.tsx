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
  TagChip: ({ slug, label }: { slug: string; label: string }) => (
    <a href={`/tasks/${slug}`}>{label}</a>
  ),
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
            num_stars: 26_414,
            introducing_paper_arxiv_id: "2602.22818",
            recommended_tasks: [{ id: "9", slug: "robotics", name: "Robotics" }],
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
    expect(screen.getByRole("navigation", { name: "Breadcrumb" })).toHaveTextContent(
      "Papers/Frameworks/LeRobot",
    );
    expect(screen.getByRole("link", { name: "Papers" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "Frameworks" })).toHaveAttribute(
      "href",
      "/frameworks",
    );
    expect(screen.queryByText(/GitHub repository/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Has code" })).toBeNull();
    expect(screen.getByRole("button", { name: "Has artifacts" })).toBeInTheDocument();
    expect(screen.queryByText("Top Domains")).toBeNull();
    const githubLink = screen.getByRole("link", { name: "huggingface/lerobot ★ 26.4K" });
    expect(githubLink).toHaveAttribute(
      "href",
      "https://github.com/huggingface/lerobot",
    );
    const introducingPaperLink = screen.getByRole("link", { name: "Introducing paper" });
    expect(introducingPaperLink).toHaveAttribute(
      "href",
      "/paper/2602.22818",
    );
    const taskLink = screen.getByRole("link", { name: "Robotics" });
    expect(taskLink).toHaveAttribute(
      "href",
      "/tasks/robotics",
    );
    const scopeLinks = githubLink.closest(".paper-feed-scope-links");
    expect(scopeLinks).not.toBeNull();
    expect(Array.from(scopeLinks!.querySelectorAll("a"))).toEqual([
      githubLink,
      introducingPaperLink,
      taskLink,
    ]);
    expect(githubLink.parentElement).toHaveClass("paper-feed-primary-links");
    expect(taskLink.parentElement).toHaveClass("paper-feed-task-tags");
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
    expect(screen.queryByRole("navigation", { name: "Breadcrumb" })).toBeNull();
  });
});
