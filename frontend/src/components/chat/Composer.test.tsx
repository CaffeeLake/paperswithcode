import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
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
    render(<QueryClientProvider client={client}><Harness onSend={onSend} /></QueryClientProvider>);
    const textarea = screen.getByRole("combobox");
    fireEvent.change(textarea, { target: { value: "@d", selectionStart: 2 } });
    expect(apiClient.searchPapers).not.toHaveBeenCalled();
    expect(await screen.findByRole("option", { name: /Deep Paper/ })).toBeInTheDocument();
    expect(apiClient.searchPapers).toHaveBeenCalledWith("d", 1, 10, "hybrid", expect.any(AbortSignal));
    fireEvent.keyDown(textarea, { key: "Enter" });
    expect(onSend).not.toHaveBeenCalled();
    expect(textarea).toHaveValue("@Deep Paper");
    expect(apiClient.prewarmChatPaperContext).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(textarea, { key: "Enter" });
    expect(onSend).toHaveBeenCalledWith(expect.objectContaining({
      text: "@Deep Paper",
      paperMentions: [expect.objectContaining({ route_id: "2501.00001", start: 0, end: 11 })],
    }));
  });
});
