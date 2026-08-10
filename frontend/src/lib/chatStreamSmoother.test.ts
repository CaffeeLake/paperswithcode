import { describe, expect, it, vi } from "vitest";

import type { ChatEvent } from "@/lib/chat";
import {
  createSmoothedChatStream,
  takeCompletedText,
} from "@/lib/chatStreamSmoother";

const source = (...events: ChatEvent[]) => (async function* () {
  for (const event of events) yield event;
})();

class VirtualClock {
  time = 0;
  sleeps: number[] = [];

  now = () => this.time;

  sleep = async (ms: number) => {
    this.sleeps.push(ms);
    this.time += ms;
  };
}

async function collect(stream: AsyncGenerator<ChatEvent>) {
  const events: ChatEvent[] = [];
  for await (const event of stream) events.push(event);
  return events;
}

describe("semantic chat stream segmentation", () => {
  it("preserves words, punctuation, whitespace, and chunk-split words exactly", () => {
    let pending = "";
    const pieces: string[] = [];
    for (const chunk of ["Hello,", "  wor", "ld!\nNext", " line "]) {
      pending += chunk;
      const split = takeCompletedText(pending);
      pieces.push(...split.pieces);
      pending = split.pending;
    }
    pieces.push(...takeCompletedText(pending, true).pieces);
    expect(pieces.join("")).toBe("Hello,  world!\nNext line ");
    expect(pieces.some((piece) => piece.includes("Hello,"))).toBe(true);
  });

  it("flushes boundaryless text in bounded 64-character pieces", () => {
    const text = "x".repeat(150);
    const first = takeCompletedText(text);
    expect(first.pieces).toEqual(["x".repeat(64)]);
    const second = takeCompletedText(first.pending);
    expect(second.pieces).toEqual(["x".repeat(64)]);
    expect(second.pending).toBe("x".repeat(22));
  });

  it("uses the whitespace fallback without normalizing input", () => {
    const intl = Intl as unknown as { Segmenter?: unknown };
    const original = intl.Segmenter;
    Object.defineProperty(intl, "Segmenter", { configurable: true, value: undefined });
    try {
      expect(takeCompletedText("hello\tworld\nnext")).toEqual({
        pieces: ["hello\t", "world\n"],
        pending: "next",
      });
    } finally {
      Object.defineProperty(intl, "Segmenter", { configurable: true, value: original });
    }
  });

  it("uses CJK semantic boundaries when Intl.Segmenter is available", () => {
    const intl = Intl as unknown as { Segmenter?: unknown };
    if (!intl.Segmenter) return;
    const split = takeCompletedText("私は研究者です");
    expect(split.pieces.length).toBeGreaterThan(0);
    expect(split.pieces.join("") + split.pending).toBe("私は研究者です");
  });

  it("is lossless across deterministic randomized chunking", () => {
    const text = "Punctuation: stays attached.  多言語の文章です。\n" + "z".repeat(70);
    for (let seed = 1; seed <= 30; seed += 1) {
      let cursor = 0;
      let pending = "";
      const output: string[] = [];
      while (cursor < text.length) {
        const width = ((seed * 17 + cursor * 13) % 9) + 1;
        pending += text.slice(cursor, cursor + width);
        cursor += width;
        const split = takeCompletedText(pending);
        output.push(...split.pieces);
        pending = split.pending;
      }
      output.push(...takeCompletedText(pending, true).pieces);
      expect(output.join("")).toBe(text);
    }
  });
});

describe("smoothed chat event ordering and timing", () => {
  it("keeps reasoning, tools, answers, and completion in semantic order", async () => {
    const clock = new VirtualClock();
    const handle = createSmoothedChatStream(source(
      { type: "reasoning_start" },
      { type: "reasoning_delta", text: "Check evidence carefully" },
      { type: "reasoning_end" },
      { type: "tool_call", id: "t1", name: "search", args: {} },
      { type: "tool_result", id: "t1", took_ms: 1, hits: 0, results: [] },
      { type: "answer_delta", text: "Final answer here" },
      { type: "done", finish_reason: "success" },
    ), { clock });
    const events = await collect(handle.events);
    expect(events.map((event) => event.type)).toEqual([
      "reasoning_start",
      "reasoning_delta",
      "reasoning_delta",
      "reasoning_delta",
      "reasoning_end",
      "tool_call",
      "tool_result",
      "answer_delta",
      "answer_delta",
      "answer_delta",
      "done",
    ]);
    expect(events.filter((event) => event.type === "reasoning_delta").map((event) => event.text).join(""))
      .toBe("Check evidence carefully");
    expect(events.filter((event) => event.type === "answer_delta").map((event) => event.text).join(""))
      .toBe("Final answer here");
    expect(clock.time).toBeLessThanOrEqual(400);
  });

  it("never merges reasoning and answer text streams", async () => {
    const handle = createSmoothedChatStream(source(
      { type: "reasoning_delta", text: "reasoning suffix" },
      { type: "answer_delta", text: "answer suffix" },
      { type: "done" },
    ), { clock: new VirtualClock() });
    const events = await collect(handle.events);
    expect(events.filter((event) => event.type === "reasoning_delta").map((event) => event.text).join(""))
      .toBe("reasoning suffix");
    expect(events.filter((event) => event.type === "answer_delta").map((event) => event.text).join(""))
      .toBe("answer suffix");
  });

  it("lets title events pass an incomplete suffix without overtaking completed text", async () => {
    const handle = createSmoothedChatStream(source(
      { type: "answer_delta", text: "complete partial" },
      { type: "session_title_delta", text: "Title" },
      { type: "answer_delta", text: " word " },
      { type: "done" },
    ), { clock: new VirtualClock() });
    const events = await collect(handle.events);
    expect(events.map((event) => event.type)).toEqual([
      "answer_delta",
      "session_title_delta",
      "answer_delta",
      "answer_delta",
      "done",
    ]);
    expect(events.filter((event) => event.type === "answer_delta").map((event) => event.text).join(""))
      .toBe("complete partial word ");
  });

  it("applies provider errors only after accepted text", async () => {
    const handle = createSmoothedChatStream(source(
      { type: "answer_delta", text: "accepted answer" },
      { type: "error", message: "provider failed", code: "provider_error" },
    ), { clock: new VirtualClock() });
    const events = await collect(handle.events);
    expect(events.map((event) => event.type)).toEqual([
      "answer_delta",
      "answer_delta",
      "error",
    ]);
  });

  it("bypasses cadence while hidden", async () => {
    const clock = new VirtualClock();
    const handle = createSmoothedChatStream(source(
      { type: "answer_delta", text: "one two three four" },
      { type: "done" },
    ), { clock, isHidden: () => true });
    await collect(handle.events);
    expect(clock.sleeps).toEqual([]);
    expect(clock.time).toBe(0);
  });

  it("returns all queued non-terminal text synchronously for explicit Stop", async () => {
    let release!: () => void;
    const blocked = new Promise<void>((resolve) => { release = resolve; });
    const input = (async function* () {
      yield { type: "answer_delta", text: "one two three four five" } as ChatEvent;
      await blocked;
      yield { type: "done" } as ChatEvent;
    })();
    const clock = new VirtualClock();
    const handle = createSmoothedChatStream(input, { clock });
    const first = await handle.events.next();
    expect(first.value).toMatchObject({ type: "answer_delta", text: "one " });
    await Promise.resolve();
    const accepted = handle.takeAcceptedForStop();
    expect(accepted.filter((event) => event.type === "answer_delta").map((event) => event.text).join(""))
      .toBe("two three four five");
    expect(accepted.some((event) => event.type === "done" || event.type === "error")).toBe(false);
    release();
  });

  it("rethrows transport errors after accepted text", async () => {
    const input = (async function* () {
      yield { type: "answer_delta", text: "accepted text" } as ChatEvent;
      throw new Error("transport failed");
    })();
    const events: ChatEvent[] = [];
    const handle = createSmoothedChatStream(input, { clock: new VirtualClock() });
    await expect((async () => {
      for await (const event of handle.events) events.push(event);
    })()).rejects.toThrow("transport failed");
    expect(events.map((event) => event.type)).toEqual(["answer_delta", "answer_delta"]);
  });

  it("cancels a pacing wait promptly and closes the consumer", async () => {
    vi.useFakeTimers();
    const controller = new AbortController();
    const handle = createSmoothedChatStream(source(
      { type: "answer_delta", text: "one two three " },
      { type: "done" },
    ), { signal: controller.signal });
    const first = await handle.events.next();
    expect(first.done).toBe(false);
    const waiting = handle.events.next();
    await Promise.resolve();
    controller.abort();
    await expect(waiting).resolves.toMatchObject({ done: true });
    expect(vi.getTimerCount()).toBe(0);
    vi.useRealTimers();
  });
});
