import { describe, expect, it, vi } from "vitest";

import { ChatLatencyTracker } from "./chatLatency";

describe("ChatLatencyTracker", () => {
  it("reports stream start, first visible content, and one terminal outcome", () => {
    const report = vi.fn();
    const tracker = new ChatLatencyTracker(100, report);

    tracker.recordStreamStart("request-1", 140);
    tracker.recordFirstVisible(175);
    tracker.recordTerminal("complete");
    tracker.recordTerminal("error");

    expect(report.mock.calls).toEqual([
      ["request-1", { submission_to_stream_start_ms: 40 }],
      ["request-1", { submission_to_first_visible_delta_ms: 75 }],
      ["request-1", { terminal_classification: "complete" }],
    ]);
  });

  it("holds an early visible measurement until the request id arrives", () => {
    const report = vi.fn();
    const tracker = new ChatLatencyTracker(100, report);

    tracker.recordFirstVisible(125);
    tracker.recordStreamStart("request-2", 150);

    expect(report.mock.calls).toEqual([
      ["request-2", { submission_to_stream_start_ms: 50 }],
      ["request-2", { submission_to_first_visible_delta_ms: 25 }],
    ]);
  });
});
