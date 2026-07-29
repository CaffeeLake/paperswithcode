import { afterEach, describe, expect, it, vi } from "vitest";

import { reportChatLatency } from "@/lib/chat";

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
