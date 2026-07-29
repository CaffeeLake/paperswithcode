import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ChatEvent, ChatMessage, ChatStreamRequest } from "@/lib/chat";
import type { ChatSessionDetail } from "@/lib/chatSessions";
import { useChat } from "@/hooks/useChat";

const { streamChatMock, getSessionMock, reportChatLatencyMock } = vi.hoisted(() => ({
  streamChatMock: vi.fn(),
  getSessionMock: vi.fn(),
  reportChatLatencyMock: vi.fn(),
}));

vi.mock("@/lib/chat", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/chat")>();
  return {
    ...actual,
    streamChat: streamChatMock,
    reportChatLatency: reportChatLatencyMock,
  };
});

vi.mock("@/lib/chatSessions", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/chatSessions")>();
  return { ...actual, getSession: getSessionMock };
});

const sessionDetail = (
  id: string,
  messages: ChatSessionDetail["messages"],
): ChatSessionDetail => ({
  id,
  title: "Original title",
  selected_model: "zai-org/GLM-5.2",
  created_at: "2026-07-28T00:00:00Z",
  updated_at: "2026-07-28T00:00:00Z",
  message_count: messages.length,
  is_busy: false,
  transcript_status: "ready",
  messages,
});

const persistedUser = (
  id: string,
  sequence: number,
  content: string,
  revision = 1,
): ChatSessionDetail["messages"][number] => ({
  id,
  turn_id: `${id}-turn`,
  sequence,
  role: "user",
  content,
  revision,
  status: "complete",
  display_blocks: [],
  citations: [],
  followups: [],
  error_code: null,
});

const persistedAssistant = (
  id: string,
  sequence: number,
  content: string,
): ChatSessionDetail["messages"][number] => ({
  id,
  turn_id: `${id}-turn`,
  sequence,
  role: "assistant",
  content,
  revision: 1,
  status: "complete",
  display_blocks: [{ kind: "answer", text: content, done: true }],
  citations: [],
  followups: [],
  error_code: null,
});

const uiTurn = (id: string, text: string): ChatMessage[] => [
  { id, role: "user", text, revision: 1, status: "complete" },
  {
    id: `${id}-answer`,
    role: "assistant",
    blocks: [{ kind: "answer", text: `Answer to ${text}`, done: true }],
  },
];

const stream = (...events: ChatEvent[]) => async function* () {
  for (const event of events) yield event;
};

const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((next) => {
    resolve = next;
  });
  return { promise, resolve };
};

const renderChat = (sessionId: string | null = "session-1") => {
  const onSessionId = vi.fn();
  const onSettled = vi.fn();
  const result = renderHook(() => useChat({
    sessionId,
    initialModel: "zai-org/GLM-5.2",
    onSessionId,
    onTitle: vi.fn(),
    onSettled,
    onInterrupted: vi.fn(),
  }));
  return { ...result, onSessionId, onSettled };
};

beforeEach(() => {
  streamChatMock.mockReset();
  getSessionMock.mockReset();
  reportChatLatencyMock.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useChat editAndResend", () => {
  it("edits the first prompt through the new-session path, including unchanged text", async () => {
    let request: ChatStreamRequest | undefined;
    streamChatMock.mockImplementation((next: ChatStreamRequest) => {
      request = next;
      return stream(
        { type: "stream_start", request_id: "r1", session_id: "session-2" },
        { type: "done", followups: [], finish_reason: "success" },
      )();
    });
    getSessionMock.mockResolvedValue(sessionDetail("session-2", [
      persistedUser("new-user", 1, "Same prompt"),
      persistedAssistant("new-answer", 2, "New answer"),
    ]));
    const { result, onSessionId } = renderChat();
    act(() => result.current.load(uiTurn("user-1", "Same prompt")));

    act(() => {
      expect(result.current.editAndResend("user-1", "Same prompt")).toBe(true);
    });

    expect(request).toMatchObject({
      message: "Same prompt",
      session_id: null,
      initial_model: "zai-org/GLM-5.2",
    });
    expect(request).not.toHaveProperty("replace_message_id");
    await waitFor(() => expect(result.current.busy).toBe(false));
    expect(onSessionId).toHaveBeenCalledWith("session-2");
    expect(result.current.messages[0]).toMatchObject({
      id: "new-user",
      text: "Same prompt",
    });
  });

  it("rewinds a later prompt optimistically and sends its id and revision", async () => {
    let request: ChatStreamRequest | undefined;
    streamChatMock.mockImplementation((next: ChatStreamRequest) => {
      request = next;
      return stream(
        { type: "stream_start", request_id: "r1", session_id: "session-1" },
        { type: "done", followups: [], finish_reason: "success" },
      )();
    });
    getSessionMock.mockResolvedValue(sessionDetail("session-1", [
      persistedUser("user-1", 1, "First"),
      persistedAssistant("answer-1", 2, "First answer"),
      persistedUser("new-user-2", 7, "Edited second", 2),
      persistedAssistant("new-answer-2", 8, "Edited answer"),
    ]));
    const { result } = renderChat();
    act(() => result.current.load([
      ...uiTurn("user-1", "First"),
      ...uiTurn("user-2", "Second"),
      ...uiTurn("user-3", "Third"),
    ]));

    act(() => {
      expect(result.current.editAndResend("user-2", "Edited second")).toBe(true);
    });

    expect(request).toMatchObject({
      session_id: "session-1",
      replace_message_id: "user-2",
      prior_revision: 1,
    });
    expect(result.current.messages.map((message) => message.id)).toEqual([
      "user-1",
      "user-1-answer",
      "user-2",
      expect.stringMatching(/^m/),
    ]);
    expect(result.current.messages[2].text).toBe("Edited second");
    await waitFor(() => expect(result.current.busy).toBe(false));
    expect(result.current.messages.map((message) => message.id)).toEqual([
      "user-1",
      "answer-1",
      "new-user-2",
      "new-answer-2",
    ]);
  });

  it("restores the exact snapshot when admission fails before stream_start", async () => {
    streamChatMock.mockImplementation(async function* () {
      yield* stream()();
      throw new Error("stale revision");
    });
    const original = [...uiTurn("user-1", "First"), ...uiTurn("user-2", "Second")];
    const { result } = renderChat();
    act(() => result.current.load(original));

    act(() => {
      expect(result.current.editAndResend("user-2", "Edited")).toBe(true);
    });

    await waitFor(() => expect(result.current.busy).toBe(false));
    expect(result.current.messages).toEqual(original);
    expect(result.current.sessionError).toBe(
      "Couldn’t resend this message. Your original conversation was restored.",
    );
    expect(getSessionMock).not.toHaveBeenCalled();
  });

  it("reloads canonical history after stream_start and reports a pre-activation restore", async () => {
    streamChatMock.mockImplementation(() => stream(
      { type: "stream_start", request_id: "r1", session_id: "session-1" },
      { type: "error", message: "fork failed", code: "replacement_prepare_failed" },
    )());
    getSessionMock.mockResolvedValue(sessionDetail("session-1", [
      persistedUser("user-1", 1, "First"),
      persistedAssistant("answer-1", 2, "First answer"),
      persistedUser("user-2", 3, "Second"),
      persistedAssistant("answer-2", 4, "Second answer"),
    ]));
    const { result } = renderChat();
    act(() => result.current.load([
      ...uiTurn("user-1", "First"),
      ...uiTurn("user-2", "Second"),
    ]));

    act(() => {
      expect(result.current.editAndResend("user-2", "Edited")).toBe(true);
    });

    await waitFor(() => expect(result.current.busy).toBe(false));
    expect(getSessionMock).toHaveBeenCalledWith("session-1");
    expect(result.current.messages[2]).toMatchObject({ id: "user-2", text: "Second" });
    expect(result.current.sessionError).toBe(
      "Couldn’t resend this message. Your original conversation was restored.",
    );
  });
});

describe("useChat canonical reloads", () => {
  it("does not overwrite a conversation loaded while a canonical reload is pending", async () => {
    const canonical = deferred<ChatSessionDetail>();
    streamChatMock.mockImplementation(() => stream(
      { type: "stream_start", request_id: "r1", session_id: "session-1" },
      { type: "done", followups: [], finish_reason: "success" },
    )());
    getSessionMock.mockReturnValue(canonical.promise);
    const { result } = renderChat();

    act(() => {
      expect(result.current.send("New turn")).toBe(true);
    });
    await waitFor(() => expect(getSessionMock).toHaveBeenCalledWith("session-1"));

    const loaded = uiTurn("other-user", "Other conversation");
    act(() => result.current.load(loaded));
    await act(async () => {
      canonical.resolve(sessionDetail("session-1", [
        persistedUser("stale-user", 1, "Stale conversation"),
      ]));
      await canonical.promise;
    });

    expect(result.current.messages).toEqual(loaded);
  });

  it("does not let an older canonical reload replace a newer request", async () => {
    const firstCanonical = deferred<ChatSessionDetail>();
    const secondCanonical = deferred<ChatSessionDetail>();
    streamChatMock
      .mockImplementationOnce(() => stream(
        { type: "stream_start", request_id: "r1", session_id: "session-1" },
        { type: "done", followups: [], finish_reason: "success" },
      )())
      .mockImplementationOnce(() => stream(
        { type: "stream_start", request_id: "r2", session_id: "session-1" },
        { type: "done", followups: [], finish_reason: "success" },
      )());
    getSessionMock
      .mockReturnValueOnce(firstCanonical.promise)
      .mockReturnValueOnce(secondCanonical.promise);
    const { result } = renderChat();

    act(() => {
      expect(result.current.send("First turn")).toBe(true);
    });
    await waitFor(() => expect(getSessionMock).toHaveBeenCalledTimes(1));

    act(() => {
      expect(result.current.send("Second turn")).toBe(true);
    });
    await waitFor(() => expect(getSessionMock).toHaveBeenCalledTimes(2));

    await act(async () => {
      firstCanonical.resolve(sessionDetail("session-1", [
        persistedUser("stale-user", 1, "Stale conversation"),
      ]));
      await firstCanonical.promise;
    });
    expect(result.current.messages.some((message) => message.text === "Second turn")).toBe(true);
    expect(result.current.messages.some((message) => message.id === "stale-user")).toBe(false);

    await act(async () => {
      secondCanonical.resolve(sessionDetail("session-1", [
        persistedUser("latest-user", 1, "Second turn"),
      ]));
      await secondCanonical.promise;
    });
    await waitFor(() => expect(result.current.messages[0]?.id).toBe("latest-user"));
  });
});

describe("useChat workspace status and browser timing", () => {
  it("shows workspace preparation at exactly 750 ms and clears it on workspace_ready", async () => {
    vi.useFakeTimers();
    const workspaceReady = deferred<void>();
    const finish = deferred<void>();
    streamChatMock.mockImplementation(async function* () {
      yield { type: "stream_start", request_id: "r1", session_id: "session-1" };
      await workspaceReady.promise;
      yield { type: "workspace_ready" };
      await finish.promise;
      yield { type: "done", finish_reason: "success" };
    });
    const { result, unmount } = renderChat();

    act(() => {
      expect(result.current.send("New turn")).toBe(true);
    });
    await act(async () => { await Promise.resolve(); });

    act(() => vi.advanceTimersByTime(749));
    expect(result.current.messages.at(-1)?.status).toBeUndefined();
    act(() => vi.advanceTimersByTime(1));
    expect(result.current.messages.at(-1)?.status).toBe(
      "Preparing research workspace…",
    );

    await act(async () => {
      workspaceReady.resolve();
      await workspaceReady.promise;
      await Promise.resolve();
    });
    expect(result.current.messages.at(-1)?.status).toBeUndefined();

    await act(async () => {
      finish.resolve();
      await finish.promise;
      await Promise.resolve();
    });
    unmount();
  });

  it("does not show workspace preparation after an earlier visible event", async () => {
    vi.useFakeTimers();
    const finish = deferred<void>();
    streamChatMock.mockImplementation(async function* () {
      yield { type: "stream_start", request_id: "r1", session_id: "session-1" };
      yield { type: "reasoning_start" };
      await finish.promise;
      yield { type: "done", finish_reason: "success" };
    });
    const { result, unmount } = renderChat();

    act(() => {
      expect(result.current.send("New turn")).toBe(true);
    });
    await act(async () => { await Promise.resolve(); });
    act(() => vi.advanceTimersByTime(750));

    expect(result.current.messages.at(-1)?.status).toBeUndefined();
    expect(result.current.messages.at(-1)?.blocks?.[0]).toMatchObject({
      kind: "reasoning",
      active: true,
    });

    await act(async () => {
      finish.resolve();
      await finish.promise;
      await Promise.resolve();
    });
    unmount();
  });

  it("reports stream start, rendered first-visible delta, and terminal status once", async () => {
    vi.useFakeTimers();
    const streamStarted = deferred<void>();
    const answerReady = deferred<void>();
    const finish = deferred<void>();
    streamChatMock.mockImplementation(async function* () {
      await streamStarted.promise;
      yield { type: "stream_start", request_id: "r1", session_id: "session-1" };
      await answerReady.promise;
      yield { type: "answer_delta", text: "Visible answer" };
      await finish.promise;
      yield { type: "done", finish_reason: "success" };
    });
    const { result, unmount } = renderChat();

    act(() => {
      expect(result.current.send("New turn")).toBe(true);
      vi.advanceTimersByTime(125);
    });
    await act(async () => {
      streamStarted.resolve();
      await streamStarted.promise;
      await Promise.resolve();
    });
    act(() => vi.advanceTimersByTime(75));
    await act(async () => {
      answerReady.resolve();
      await answerReady.promise;
      await Promise.resolve();
    });

    expect(reportChatLatencyMock).toHaveBeenCalledWith("r1", {
      submission_to_stream_start_ms: expect.any(Number),
    });
    expect(reportChatLatencyMock).toHaveBeenCalledWith("r1", {
      submission_to_first_visible_delta_ms: expect.any(Number),
    });
    const streamStartMs = reportChatLatencyMock.mock.calls[0][1]
      .submission_to_stream_start_ms;
    const firstVisibleMs = reportChatLatencyMock.mock.calls[1][1]
      .submission_to_first_visible_delta_ms;
    expect(streamStartMs).toBeGreaterThanOrEqual(0);
    expect(firstVisibleMs).toBeGreaterThanOrEqual(streamStartMs);

    await act(async () => {
      finish.resolve();
      await finish.promise;
      await Promise.resolve();
    });
    expect(reportChatLatencyMock).toHaveBeenCalledWith("r1", {
      terminal_classification: "complete",
    });
    expect(reportChatLatencyMock).toHaveBeenCalledTimes(3);
    unmount();
  });
});
