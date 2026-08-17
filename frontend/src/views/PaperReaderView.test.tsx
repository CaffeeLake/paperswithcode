import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getAvailability: vi.fn(),
}));

vi.mock("@/hooks/usePapers", () => ({
  usePaper: () => ({
    data: {
      id: "42",
      arxiv_id: "1706.03762",
      title: "Attention Is All You Need",
      source: "arxiv",
      url_pdf: "https://arxiv.org/pdf/1706.03762v7.pdf",
    },
    isLoading: false,
    error: null,
  }),
}));
vi.mock("@/lib/authContext", () => ({
  useAuth: () => ({ user: { username: "reviewer" }, logout: vi.fn() }),
}));
vi.mock("@/lib/api/chat", () => ({
  chatApi: { getAvailability: mocks.getAvailability },
}));
vi.mock("@/components/UserMenu", () => ({ default: () => <div>User menu</div> }));
vi.mock("@/components/HfSignInButton", () => ({ default: () => <button>Sign in</button> }));
vi.mock("@/components/pdf/PdfViewer", () => ({
  PdfViewer: ({ url }: { url: string }) => <div role="region" aria-label="Paper PDF" data-url={url}>PDF viewer</div>,
}));
vi.mock("@/views/ChatView", () => ({
  ChatExperience: () => <div>Paper assistant</div>,
}));

import PaperReaderView from "@/views/PaperReaderView";

function renderReader() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/pdf/1706.03762"]}>
        <Routes><Route path="/pdf/:arxivId" element={<PaperReaderView />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("PaperReaderView", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.stubEnv("VITE_CHAT_ENABLED", "1");
    vi.stubEnv("VITE_PAPER_READER_CHAT_ENABLED", "1");
    mocks.getAvailability.mockResolvedValue({
      status: "available",
      reason: null,
      expected_recovery_at: null,
      paper_mentions_enabled: true,
      web_search_available: true,
      native_pdf_reader_enabled: true,
      paper_reader_chat_enabled: true,
      paper_reader_selection_enabled: false,
    });
  });

  afterEach(() => vi.unstubAllEnvs());

  it("renders the linked title, PDF, and Assistant-only workspace", async () => {
    renderReader();

    expect(screen.getByRole("link", { name: /Attention Is All You Need/ }))
      .toHaveAttribute("href", "/paper/1706.03762");
    expect(screen.getByRole("region", { name: "Paper PDF" })).toBeVisible();
    expect(screen.getByRole("region", { name: "Paper PDF" }))
      .toHaveAttribute("data-url", "https://arxiv.org/pdf/1706.03762v7");
    fireEvent.click(screen.getByRole("tab", { name: "Assistant" }));
    expect(screen.getByText("Paper assistant")).toBeVisible();
    expect(screen.queryByText("Notes")).not.toBeInTheDocument();
    await waitFor(() => expect(mocks.getAvailability).toHaveBeenCalled());
  });

  it("keeps the public PDF surface but disables Assistant when the live gate closes", async () => {
    mocks.getAvailability.mockResolvedValueOnce({
      status: "available",
      reason: null,
      expected_recovery_at: null,
      paper_mentions_enabled: true,
      web_search_available: true,
      native_pdf_reader_enabled: true,
      paper_reader_chat_enabled: false,
      paper_reader_selection_enabled: false,
    });
    renderReader();

    expect(screen.getByRole("region", { name: "Paper PDF" })).toBeVisible();
    fireEvent.click(screen.getByRole("tab", { name: "Assistant" }));
    expect(await screen.findByText("Assistant is not enabled for this preview."))
      .toBeVisible();
  });
});
