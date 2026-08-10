import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Composer from "./Composer";
import { apiClient, type Paper } from "@/lib/api";
import type { ChatDraft } from "@/lib/chat";

const paper: Paper = {
  id: "42", arxiv_id: "2501.00001", source: "arxiv", source_url: null,
  url_abs: "https://arxiv.org/abs/2501.00001", url_pdf: null,
  title: "Deep Paper", abstract: "", authors: [], published: "2026-01-01",
  version: "v1", is_latest_version: true, citation_count: 0,
};
const secondPaper: Paper = { ...paper, id: "43", arxiv_id: "2502.00002", title: "Ovis" };

function Harness({ onSend }: { onSend: (draft: ChatDraft) => void }) {
  const [draft, setDraft] = React.useState<ChatDraft>({ text: "", paperMentions: [] });
  return <Composer draft={draft} onDraftChange={setDraft} onSend={onSend} paperMentionsEnabled />;
}

describe("Composer paper mentions", () => {
  beforeEach(() => {
    vi.spyOn(apiClient, "searchPapers").mockResolvedValue({ next_page: null, previous_page: null, results: [paper] });
    vi.spyOn(apiClient, "prewarmChatPaperContext").mockResolvedValue(undefined);
  });
  afterEach(() => { vi.restoreAllMocks(); });

  it("debounces hybrid search, lets Enter attach before sending, and prewarms once", async () => {
    const onSend = vi.fn();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container } = render(<QueryClientProvider client={client}><Harness onSend={onSend} /></QueryClientProvider>);
    const textarea = screen.getByRole("combobox");
    fireEvent.change(textarea, { target: { value: "@d", selectionStart: 2 } });
    expect(apiClient.searchPapers).not.toHaveBeenCalled();
    expect(await screen.findByRole("option", { name: /Deep Paper/ })).toBeInTheDocument();
    expect(apiClient.searchPapers).toHaveBeenCalledWith("d", 1, 10, "hybrid", expect.any(AbortSignal));
    fireEvent.keyDown(textarea, { key: "Enter" });
    expect(onSend).not.toHaveBeenCalled();
    expect(textarea).toHaveValue("Deep Paper");
    expect(container.querySelector(".chat-paper-inline-highlight")).toHaveTextContent("Deep Paper");
    expect(screen.queryByLabelText("Attached papers")).not.toBeInTheDocument();
    expect(apiClient.prewarmChatPaperContext).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(textarea, { key: "Enter" });
    expect(onSend).toHaveBeenCalledWith(expect.objectContaining({
      text: "Deep Paper",
      paperMentions: [expect.objectContaining({ route_id: "2501.00001", start: 0, end: 10 })],
    }));
  });

  it("shows a directly accessible sticky web-search switch when available", () => {
    const onWebSearchChange = vi.fn();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { rerender } = render(
      <QueryClientProvider client={client}>
        <Composer
          onSend={vi.fn()}
          webSearchAvailable
          webSearchEnabled={false}
          onWebSearchChange={onWebSearchChange}
        />
      </QueryClientProvider>,
    );
    const toggle = screen.getByRole("switch", { name: "Web search" });
    expect(toggle).toHaveAttribute("aria-checked", "false");
    expect(toggle).toHaveAttribute("title", expect.stringContaining("Exa"));
    fireEvent.click(toggle);
    expect(onWebSearchChange).toHaveBeenCalledWith(true);

    rerender(
      <QueryClientProvider client={client}>
        <Composer
          onSend={vi.fn()}
          busy
          webSearchAvailable
          webSearchEnabled
          onWebSearchChange={onWebSearchChange}
        />
      </QueryClientProvider>,
    );
    expect(screen.getByRole("switch", { name: "Web search" })).toBeDisabled();
  });

  it("highlights multiple selected papers in place inside a sentence", async () => {
    vi.mocked(apiClient.searchPapers).mockImplementation(async (query) => ({
      next_page: null,
      previous_page: null,
      results: query === "ovi" ? [secondPaper] : [paper],
    }));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container } = render(
      <QueryClientProvider client={client}><Harness onSend={vi.fn()} /></QueryClientProvider>,
    );
    const textarea = screen.getByRole("combobox");

    fireEvent.change(textarea, { target: { value: "How does @dee", selectionStart: 13 } });
    expect(await screen.findByRole("option", { name: /Deep Paper/ })).toBeInTheDocument();
    fireEvent.keyDown(textarea, { key: "Enter" });
    await waitFor(() => expect(textarea).toHaveValue("How does Deep Paper"));
    fireEvent.change(textarea, {
      target: { value: "How does Deep Paper compare to @ovi", selectionStart: 35 },
    });
    (textarea as HTMLTextAreaElement).setSelectionRange(35, 35);
    fireEvent.select(textarea);
    expect(await screen.findByRole("option", { name: /Ovis/ })).toBeInTheDocument();
    fireEvent.keyDown(textarea, { key: "Enter" });
    fireEvent.change(textarea, {
      target: { value: "How does Deep Paper compare to Ovis?", selectionStart: 36 },
    });

    expect(textarea).toHaveValue("How does Deep Paper compare to Ovis?");
    expect([...container.querySelectorAll(".chat-paper-inline-highlight")].map((node) => node.textContent))
      .toEqual(["Deep Paper", "Ovis"]);
    expect(screen.queryByLabelText("Attached papers")).not.toBeInTheDocument();
  });
});
