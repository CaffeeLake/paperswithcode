import { afterEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/lib/api";

afterEach(() => vi.unstubAllGlobals());

describe("framework/repository paper API filters", () => {
  it("serializes framework and repository filters with the feed controls", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      count: 0,
      next_page: null,
      previous_page: null,
      results: [],
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    await apiClient.getPapers({
      repository: "https://github.com/HuggingFace/LeRobot",
      search: "robot",
      order_by: "trending",
      time: "month",
      has_hf_artifacts: true,
    });

    const requestedUrl = String(fetchMock.mock.calls[0][0]);
    expect(requestedUrl).toContain("repository=https%3A%2F%2Fgithub.com%2FHuggingFace%2FLeRobot");
    expect(requestedUrl).toContain("search=robot");
    expect(requestedUrl).toContain("order_by=trending");
    expect(requestedUrl).toContain("time=month");
    expect(requestedUrl).toContain("has_hf_artifacts=true");
  });
});
