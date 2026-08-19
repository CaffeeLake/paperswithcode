import { describe, expect, it } from "vitest";

import type { ChatMessage } from "./chat";
import { chatLifecycleReducer, initialChatLifecycle } from "./chatLifecycle";

const streaming = (): ChatMessage[] => [{
  id: "assistant",
  role: "assistant",
  streaming: true,
  blocks: [],
}];

describe("chatLifecycleReducer", () => {
  it("renders truthful lifecycle phases without adding semantic blocks", () => {
    let state = chatLifecycleReducer(initialChatLifecycle(), {
      type: "start",
      messages: streaming(),
      sessionId: null,
    });
    state = chatLifecycleReducer(state, {
      type: "event",
      event: { type: "lifecycle", phase: "preparing_workspace" },
    });
    expect(state.messages[0]).toMatchObject({
      status: "Preparing secure workspace…",
      blocks: [],
    });
    state = chatLifecycleReducer(state, {
      type: "event",
      event: { type: "reasoning_start" },
    });
    expect(state.messages[0].status).toBeUndefined();
  });

  it("projects stream events and terminal completion without mutation", () => {
    const started = chatLifecycleReducer(initialChatLifecycle(), {
      type: "start",
      messages: streaming(),
      sessionId: null,
    });
    const admitted = chatLifecycleReducer(started, {
      type: "event",
      event: {
        type: "stream_start",
        session_id: "session-1",
        request_id: "request-1",
        provider_execution: true,
      },
    });
    const answered = chatLifecycleReducer(admitted, {
      type: "event",
      event: { type: "answer_delta", text: "Hello" },
    });
    const completed = chatLifecycleReducer(answered, {
      type: "event",
      event: { type: "done", citations: [], followups: [], finish_reason: "stop" },
    });

    expect(started.messages[0].blocks).toEqual([]);
    expect(completed).toMatchObject({ sessionId: "session-1", phase: "complete" });
    expect(completed.messages[0]).toMatchObject({
      streaming: false,
      blocks: [{ kind: "answer", text: "Hello", done: true }],
    });
  });

  it("buffers title, tool, reasoning, and error transitions explicitly", () => {
    const actions = [
      { type: "start", messages: streaming(), sessionId: "session-1" },
      { type: "event", event: { type: "session_title_start" } },
      { type: "event", event: { type: "session_title_delta", text: "  New  " } },
      { type: "event", event: { type: "session_title_delta", text: "title" } },
      { type: "event", event: { type: "reasoning_start" } },
      { type: "event", event: { type: "reasoning_delta", text: "Plan" } },
      { type: "event", event: { type: "reasoning_end" } },
      { type: "event", event: { type: "tool_call", id: "tool-1", name: "search", args: {} } },
      { type: "event", event: { type: "error", message: "Failed", code: "provider_error" } },
    ] as const;
    const state = actions.reduce(chatLifecycleReducer, initialChatLifecycle());

    expect(state.title).toBe(" New title");
    expect(state.phase).toBe("failed");
    expect(state.messages[0]).toMatchObject({ error: "Failed", errorCode: "provider_error" });
    expect(state.messages[0].blocks).toEqual([
      { kind: "reasoning", text: "Plan", active: false, open: false },
      expect.objectContaining({ kind: "tool", id: "tool-1", status: "running" }),
    ]);
  });

  it("turns an in-flight projection into an explicit stopped terminal state", () => {
    const started = chatLifecycleReducer(initialChatLifecycle(), {
      type: "start",
      messages: [{
        ...streaming()[0],
        blocks: [
          { kind: "reasoning", text: "Partial", active: true, open: true },
          { kind: "tool", id: "tool-1", name: "search", args: {}, status: "running", open: false },
          { kind: "answer", text: "Answer", done: false },
        ],
      }],
      sessionId: "session-1",
    });

    const stopped = chatLifecycleReducer(started, { type: "stop" });

    expect(stopped.phase).toBe("stopped");
    expect(stopped.messages[0]).toMatchObject({ streaming: false, finishReason: "stopped" });
    expect(stopped.messages[0].blocks).toEqual([
      { kind: "reasoning", text: "Partial", active: false, open: false },
      { kind: "answer", text: "Answer", done: true },
    ]);
  });

  it("projects Excalidraw App events without wiping the in-flight assistant", () => {
    let state = chatLifecycleReducer(initialChatLifecycle(), {
      type: "start",
      messages: streaming(),
      sessionId: "session-1",
    });
    state = chatLifecycleReducer(state, {
      type: "event",
      event: {
        type: "app_start",
        id: "tool-app-1",
        instance_id: "tool-app-1",
        provider: "excalidraw",
        server: "excalidraw",
        tool: "create_view",
        resource_uri: "ui://excalidraw/mcp-app.html",
        input: { elements: "[]" },
      },
    });
    state = chatLifecycleReducer(state, {
      type: "event",
      event: {
        type: "app_result",
        id: "tool-app-1",
        status: "ready",
        took_ms: 18,
        result: {
          content: [{ type: "text", text: "ok", truncated: false }],
          structuredContent: {},
          isError: false,
        },
      },
    });
    state = chatLifecycleReducer(state, {
      type: "event",
      event: { type: "answer_delta", text: "Here is the schematic." },
    });

    expect(state.messages[0].blocks).toEqual([
      {
        kind: "app",
        schema_version: 1,
        instance_id: "tool-app-1",
        provider: "excalidraw",
        server: "excalidraw",
        tool: "create_view",
        resource_uri: "ui://excalidraw/mcp-app.html",
        status: "ready",
        input: { elements: "[]" },
        result: {
          content: [{ type: "text", text: "ok", truncated: false }],
          structuredContent: {},
          isError: false,
        },
        csp: {},
        permissions: { clipboardWrite: true },
        height: 525,
      },
      { kind: "answer", text: "Here is the schematic.", done: false },
    ]);
  });
});
