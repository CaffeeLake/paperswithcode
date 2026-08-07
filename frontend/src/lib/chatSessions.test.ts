import { describe, expect, it } from "vitest";

import { toUiMessages, type ChatSessionDetail } from "@/lib/chatSessions";

describe("toUiMessages", () => {
  it.each([
    ["hf_inference_billing_exhausted", /could not bill/],
    ["hf_inference_credential_expired", /authorization expired/],
    ["provider_rate_limit", /temporarily rate-limited/],
    ["provider_timeout", /timed out/],
    ["provider_unavailable", /provider failed/],
  ])("keeps %s visibly distinct after reload", (errorCode, message) => {
    const detail: ChatSessionDetail = {
      id: "session-errors",
      title: "Test",
      selected_model: "zai-org/GLM-5.2",
      created_at: "2026-07-31T00:00:00Z",
      updated_at: "2026-07-31T00:00:00Z",
      message_count: 1,
      is_busy: false,
      web_search_enabled: false,
      transcript_status: "ready",
      messages: [{
        id: "user-error",
        turn_id: "turn-error",
        sequence: 1,
        role: "user",
        content: "Question",
        revision: 1,
        status: "error",
        display_blocks: [],
        citations: [],
        followups: [],
        error_code: errorCode,
      }],
    };

    expect(toUiMessages(detail)[1].error).toMatch(message);
    expect(toUiMessages(detail)[1].errorCode).toBe(errorCode);
  });

  it("collapses duplicate reasoning already stored in a session", () => {
    const detail: ChatSessionDetail = {
      id: "session-1",
      title: "Test",
      selected_model: "openai/gpt-5.6-luna",
      created_at: "2026-07-31T00:00:00Z",
      updated_at: "2026-07-31T00:00:00Z",
      message_count: 1,
      is_busy: false,
      web_search_enabled: false,
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
