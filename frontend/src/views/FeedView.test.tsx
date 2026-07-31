import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import {
  CHAT_AUTO_SEND_KEY,
  CHAT_DRAFT_KEY,
  CHAT_MODEL_KEY,
} from "@/lib/chatLaunch";
import { DEFAULT_CHAT_MODEL } from "@/lib/chatSessions";
import { SUGGESTED_CHAT_PROMPTS } from "@/lib/chatPrompts";
import { AskAssistant } from "@/views/FeedView";

beforeEach(() => {
  sessionStorage.clear();
});

describe("AskAssistant", () => {
  it("launches chat from each shared suggested prompt", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<AskAssistant />} />
          <Route path="/chat" element={<div>Chat launched</div>} />
        </Routes>
      </MemoryRouter>,
    );

    const exampleButtons = screen.getAllByRole("button")
      .filter((button) => SUGGESTED_CHAT_PROMPTS.includes(
        button.textContent as typeof SUGGESTED_CHAT_PROMPTS[number],
      ));
    expect(exampleButtons).toHaveLength(SUGGESTED_CHAT_PROMPTS.length);

    await user.click(screen.getByRole("button", { name: SUGGESTED_CHAT_PROMPTS[1] }));

    expect(await screen.findByText("Chat launched")).toBeInTheDocument();
    expect(sessionStorage.getItem(CHAT_DRAFT_KEY)).toBe(SUGGESTED_CHAT_PROMPTS[1]);
    expect(sessionStorage.getItem(CHAT_MODEL_KEY)).toBe(DEFAULT_CHAT_MODEL);
    expect(sessionStorage.getItem(CHAT_AUTO_SEND_KEY)).toBe("1");
  });
});
