import React from "react";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  CHAT_AUTO_SEND_KEY,
  CHAT_DRAFT_KEY,
  CHAT_MODEL_KEY,
} from "@/lib/chatLaunch";
import { DEFAULT_CHAT_MODEL, FALLBACK_CHAT_MODELS } from "@/lib/chatSessions";
import { SUGGESTED_CHAT_PROMPTS } from "@/lib/chatPrompts";
import { AskAssistant } from "@/views/FeedView";

beforeEach(() => {
  sessionStorage.clear();
});

afterEach(() => {
  vi.useRealTimers();
});

const renderAskAssistant = () => render(
  <MemoryRouter initialEntries={["/"]}>
    <Routes>
      <Route path="/" element={<AskAssistant />} />
      <Route path="/chat" element={<div>Chat launched</div>} />
    </Routes>
  </MemoryRouter>,
);

describe("AskAssistant", () => {
  it("offers the staging OpenRouter model from the shared picker list", () => {
    expect(FALLBACK_CHAT_MODELS).toContainEqual({
      id: "deepseek-ai/DeepSeek-V4-Flash-0731",
      label: "DeepSeek V4 Flash 0731",
      provider: "openrouter",
    });
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

  it("shows three sample prompt bubbles", () => {
    renderAskAssistant();

    SUGGESTED_CHAT_PROMPTS.forEach((prompt) => {
      expect(screen.getByRole("button", { name: new RegExp(prompt, "i") })).toBeInTheDocument();
    });
  });

  it("launches chat from a suggested starting point", async () => {
    const user = userEvent.setup();
    renderAskAssistant();

    await user.click(screen.getByRole("button", { name: /retrieval-augmented generation/i }));

    expect(await screen.findByText("Chat launched")).toBeInTheDocument();
    expect(sessionStorage.getItem(CHAT_DRAFT_KEY)).toBe(SUGGESTED_CHAT_PROMPTS[1]);
    expect(sessionStorage.getItem(CHAT_MODEL_KEY)).toBe(DEFAULT_CHAT_MODEL);
    expect(sessionStorage.getItem(CHAT_AUTO_SEND_KEY)).toBe("1");
  });

  it("launches chat with the typed question", async () => {
    const user = userEvent.setup();
    renderAskAssistant();
    const question = "Compare recent vision-language models";

    await user.type(screen.getByRole("textbox", { name: "Ask the assistant" }), question);
    await user.click(screen.getByRole("button", { name: "Ask the assistant" }));

    expect(await screen.findByText("Chat launched")).toBeInTheDocument();
    expect(sessionStorage.getItem(CHAT_DRAFT_KEY)).toBe(question);
    expect(sessionStorage.getItem(CHAT_MODEL_KEY)).toBe(DEFAULT_CHAT_MODEL);
    expect(sessionStorage.getItem(CHAT_AUTO_SEND_KEY)).toBe("1");
  });
});
