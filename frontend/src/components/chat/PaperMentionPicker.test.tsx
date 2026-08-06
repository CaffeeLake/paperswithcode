import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PaperMentionPicker } from "./PaperMentionPicker";
import type { Paper } from "@/lib/api";

const paper = (id: string, title: string, arxivId: string | null): Paper => ({
  id, arxiv_id: arxivId, source: arxivId ? "arxiv" : "external",
  source_url: arxivId ? null : "https://example.com/release", url_abs: null,
  url_pdf: null, title, abstract: "", authors: [], published: "2026-01-01",
  version: "v1", is_latest_version: true, citation_count: 0,
});
describe("PaperMentionPicker", () => {
  it("renders arXiv and external identities and selects before blur", () => {
    const select = vi.fn();
    const papers = [paper("1", "First", "2501.00001"), paper("2", "Second", null)];
    render(<PaperMentionPicker open query="p" results={papers} activeIndex={1} loading={false} error={false} onSelect={select} />);
    expect(screen.getByText("2501.00001")).toBeInTheDocument();
    expect(screen.getByText("example.com")).toBeInTheDocument();
    const option = screen.getByRole("option", { name: /Second/ });
    expect(option).toHaveAttribute("aria-selected", "true");
    fireEvent.mouseDown(option);
    expect(select).toHaveBeenCalledWith(papers[1]);
  });

  it("announces bare, loading, empty, and error states", () => {
    const { rerender } = render(<PaperMentionPicker open query="" results={[]} activeIndex={0} loading={false} error={false} onSelect={() => undefined} />);
    expect(screen.getByRole("status")).toHaveTextContent("Type to search papers");
    rerender(<PaperMentionPicker open query="x" results={[]} activeIndex={0} loading error={false} onSelect={() => undefined} />);
    expect(screen.getByRole("status")).toHaveTextContent("Searching papers");
    rerender(<PaperMentionPicker open query="x" results={[]} activeIndex={0} loading={false} error onSelect={() => undefined} />);
    expect(screen.getByRole("status")).toHaveTextContent("unavailable");
  });
});
