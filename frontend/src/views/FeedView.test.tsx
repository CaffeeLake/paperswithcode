import React from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  CHAT_AUTO_SEND_KEY,
  CHAT_DRAFT_KEY,
  CHAT_MODEL_KEY,
  CHAT_WEB_SEARCH_KEY,
} from "@/lib/chatLaunch";
import { apiClient } from "@/lib/api";
import { DEFAULT_CHAT_MODEL, FALLBACK_CHAT_MODELS } from "@/lib/chatSessions";
import { SUGGESTED_CHAT_PROMPTS } from "@/lib/chatPrompts";
import { AskAssistant } from "@/views/FeedView";

vi.mock("@/lib/authContext", () => ({
  useAuth: () => ({ user: { username: "owner" }, isLoading: false }),
}));

beforeEach(() => {
  sessionStorage.clear();
  vi.stubEnv("MODE", "staging");
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

const renderAskAssistant = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<AskAssistant />} />
          <Route path="/chat/:sessionId" element={<div>Dedicated chat launched</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

describe("AskAssistant", () => {
  it("offers the Hugging Face DeepSeek and staging OpenRouter models", () => {
    expect(FALLBACK_CHAT_MODELS).toContainEqual({
      id: "deepseek-ai/DeepSeek-V4-Flash-0731",
      label: "DeepSeek V4 Flash",
      provider: "huggingface",
    });
    expect(FALLBACK_CHAT_MODELS).toContainEqual({
      id: "openai/gpt-5.6-luna",
      label: "GPT-5.6 Luna (medium)",
      provider: "openrouter",
    });
    expect(FALLBACK_CHAT_MODELS).toContainEqual({
      id: "openai/gpt-5.6-terra",
      label: "GPT-5.6 Terra (medium)",
      provider: "openrouter",
    });
  });

  it("shows only a read-only DeepSeek label in the production preview", () => {
    vi.stubEnv("MODE", "production");
    renderAskAssistant();

    expect(screen.getByLabelText("Research model")).toHaveTextContent(
      "DeepSeek V4 Flash",
    );
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.queryByText(/Luna|Terra|OpenRouter/)).not.toBeInTheDocument();
  });

  it("types, holds, erases, and rotates the suggested placeholder", () => {
    vi.useFakeTimers();
    renderAskAssistant();
    const textarea = screen.getByRole("textbox", { name: "Ask the assistant" });
    const firstPrompt = SUGGESTED_CHAT_PROMPTS[0];

    expect(textarea).toHaveAttribute("placeholder", firstPrompt.slice(0, 1));

    act(() => vi.advanceTimersByTime(45 * (firstPrompt.length - 1)));
    expect(textarea).toHaveAttribute("placeholder", firstPrompt);

    act(() => vi.advanceTimersByTime(1_800));
    expect(textarea).toHaveAttribute("placeholder", firstPrompt.slice(0, -1));

    act(() => vi.advanceTimersByTime(25 * (firstPrompt.length - 1) + 350));
    expect(textarea).toHaveAttribute("placeholder", SUGGESTED_CHAT_PROMPTS[1].slice(0, 1));
  });

  it("launches chat with the typed question", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response(JSON.stringify({
      id: "11111111-1111-4111-8111-111111111111",
      title: "New chat",
      selected_model: DEFAULT_CHAT_MODEL,
      created_at: "2026-08-03T00:00:00Z",
      updated_at: "2026-08-03T00:00:00Z",
      message_count: 0,
      is_busy: false,
    }), { status: 201, headers: { "Content-Type": "application/json" } }));
    const user = userEvent.setup();
    renderAskAssistant();
    const question = "Compare recent vision-language models";

    await user.type(screen.getByRole("textbox", { name: "Ask the assistant" }), question);
    await user.click(screen.getByRole("button", { name: "Ask the assistant" }));

    expect(await screen.findByText("Dedicated chat launched")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/chat/sessions"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ selected_model: DEFAULT_CHAT_MODEL }),
      }),
    );
    expect(sessionStorage.getItem(CHAT_DRAFT_KEY)).toBe(question);
    expect(sessionStorage.getItem(CHAT_MODEL_KEY)).toBe(DEFAULT_CHAT_MODEL);
    expect(sessionStorage.getItem(CHAT_AUTO_SEND_KEY)).toBe("1");
  });

  it("offers available web search and carries the choice into the new chat", async () => {
    vi.stubEnv("VITE_CHAT_ENABLED", "1");
    vi.spyOn(apiClient, "getChatAvailability").mockResolvedValue({
      status: "available",
      reason: null,
      expected_recovery_at: null,
      paper_mentions_enabled: true,
      web_search_available: true,
    });
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response(JSON.stringify({
      id: "11111111-1111-4111-8111-111111111111",
      title: "New chat",
      selected_model: DEFAULT_CHAT_MODEL,
      created_at: "2026-08-03T00:00:00Z",
      updated_at: "2026-08-03T00:00:00Z",
      message_count: 0,
      is_busy: false,
      web_search_enabled: false,
    }), { status: 201, headers: { "Content-Type": "application/json" } }));
    const user = userEvent.setup();
    renderAskAssistant();

    const toggle = await screen.findByRole("switch", { name: "Web search" });
    await user.click(toggle);
    await user.type(
      screen.getByRole("textbox", { name: "Ask the assistant" }),
      "Find the latest vision-language model release",
    );
    await user.click(screen.getByRole("button", { name: "Ask the assistant" }));

    expect(await screen.findByText("Dedicated chat launched")).toBeInTheDocument();
    expect(sessionStorage.getItem(CHAT_WEB_SEARCH_KEY)).toBe("1");
  });

  it("hides web search when the feature is unavailable", async () => {
    vi.stubEnv("VITE_CHAT_ENABLED", "1");
    const availability = vi.spyOn(apiClient, "getChatAvailability").mockResolvedValue({
      status: "available",
      reason: null,
      expected_recovery_at: null,
      paper_mentions_enabled: true,
      web_search_available: false,
    });
    renderAskAssistant();

    await waitFor(() => expect(availability).toHaveBeenCalledTimes(1));

    expect(screen.queryByRole("switch", { name: "Web search" })).not.toBeInTheDocument();
  });
});
