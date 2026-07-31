import { describe, expect, it } from "vitest";

import { toUiMessages, type ChatSessionDetail } from "@/lib/chatSessions";

describe("toUiMessages", () => {
  it("collapses duplicate reasoning already stored in a session", () => {
    const detail: ChatSessionDetail = {
      id: "session-1",
      title: "Test",
      selected_model: "openai/gpt-5.6-luna",
      created_at: "2026-07-31T00:00:00Z",
      updated_at: "2026-07-31T00:00:00Z",
      message_count: 1,
      is_busy: false,
      transcript_status: "ready",
      messages: [{
        id: "assistant-1",
        turn_id: "turn-1",
        sequence: 1,
        role: "assistant",
        content: "Answer",
        revision: 1,
        status: "complete",
        display_blocks: [
          { kind: "reasoning", text: "**Same plan**", active: false, open: false },
          { kind: "reasoning", text: "**Same plan**", active: false, open: false },
          { kind: "answer", text: "Answer", done: true },
        ],
        citations: [],
        followups: [],
        error_code: null,
      }],
    };

    expect(toUiMessages(detail)[0].blocks).toEqual([
      { kind: "reasoning", text: "**Same plan**", active: false, open: false },
      { kind: "answer", text: "Answer", done: true },
    ]);
  });
});
