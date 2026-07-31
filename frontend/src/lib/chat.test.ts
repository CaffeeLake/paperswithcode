import { afterEach, describe, expect, it, vi } from "vitest";

import { ChatStreamError, reportChatLatency, streamChat } from "@/lib/chat";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("reportChatLatency", () => {
  it("posts same-origin best-effort timing without affecting the caller", async () => {
    vi.stubEnv("VITE_CHAT_LIVE", "1");
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    reportChatLatency("request/id", {
      submission_to_stream_start_ms: 125.5,
    });

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/chat/latency/request%2Fid"),
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        keepalive: true,
        body: JSON.stringify({ submission_to_stream_start_ms: 125.5 }),
      }),
    );
  });

  it("swallows reporting failures", async () => {
    vi.stubEnv("VITE_CHAT_LIVE", "1");
    const fetchMock = vi.fn().mockRejectedValue(new Error("offline"));
    vi.stubGlobal("fetch", fetchMock);

    expect(() => reportChatLatency(
      "r1",
      { terminal_classification: "network_error" },
    )).not.toThrow();
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  });
});

describe("streamChat access failures", () => {
  it("turns an unstructured staging 403 into an actionable error", async () => {
    vi.stubEnv("VITE_CHAT_LIVE", "1");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("Forbidden", {
      status: 403,
      headers: { "Content-Type": "text/plain" },
    })));

    const events = streamChat({
      message: "Continue from a shared chat",
      session_id: null,
      client_message_id: "message-1",
    });

    await expect(events.next()).rejects.toMatchObject({
      name: "ChatStreamError",
      code: "staging_access_required",
      message: expect.stringContaining("limited to approved Hugging Face users"),
    } satisfies Partial<ChatStreamError>);
  });
});
