import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { apiClient, type Paper } from "@/lib/api";
import AuthorDetailView from "@/views/AuthorDetailView";

const paper: Paper = {
  id: "42",
  arxiv_id: "2607.24653",
  source: "arxiv",
  source_url: "https://arxiv.org/abs/2607.24653",
  url_abs: "https://arxiv.org/abs/2607.24653",
  url_pdf: null,
  title: "Kimi K3",
  abstract: "Technical report.",
  authors: ["Researcher"],
  published: "2026-07-27",
  version: "v1",
  is_latest_version: true,
  citation_count: 0,
};

afterEach(() => vi.restoreAllMocks());

describe("AuthorDetailView", () => {
  it("loads the stable author ID route and renders canonical paper links", async () => {
    vi.spyOn(apiClient, "getAuthor").mockResolvedValue({
      id: "7",
      full_name: "Researcher",
      hf_username: "researcher",
      paper_count: 1,
    });
    vi.spyOn(apiClient, "getAuthorPapers").mockResolvedValue({
      count: 1,
      next_page: null,
      previous_page: null,
      results: [paper],
    });
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/authors/7"]}>
          <Routes>
            <Route path="/authors/:authorId" element={<AuthorDetailView />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByRole("heading", { name: "Researcher" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Kimi K3" })).toHaveAttribute(
      "href",
      "/paper/2607.24653",
    );
    expect(apiClient.getAuthor).toHaveBeenCalledWith("7");
  });
});
