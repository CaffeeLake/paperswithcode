import assert from "node:assert/strict";
import test from "node:test";
import { PiEventAdapter } from "../src/events.js";

test("maps hidden thinking, text, tools, usage, and correlations", () => {
  const semantic: string[] = [];
  const adapter = new PiEventAdapter(false, (kind) => semantic.push(kind));
  assert.deepEqual(
    adapter.feed({
      type: "message_update",
      assistantMessageEvent: { type: "thinking_delta", delta: "secret reasoning" },
    }),
    [],
  );
  assert.deepEqual(
    adapter.feed({ type: "tool_execution_start", toolCallId: "t1", toolName: "bash", args: { command: "pwc version" } }),
    [{ type: "tool_call", id: "t1", name: "Bash", args: { command: "pwc version" } }],
  );
  assert.equal(adapter.feed({ type: "tool_execution_end", toolCallId: "t1", result: { content: [{ type: "text", text: "ok" }] }, isError: false })[0]?.type, "tool_result");
  assert.deepEqual(
    adapter.feed({ type: "message_update", assistantMessageEvent: { type: "text_delta", delta: "Answer" } }),
    [{ type: "answer_delta", text: "Answer" }],
  );
  assert.deepEqual(semantic, ["reasoning", "tool", "answer"]);
  assert.throws(() => adapter.feed({ type: "tool_execution_end", toolCallId: "missing", result: {}, isError: false }));
});

test("closes visible reasoning before answer", () => {
  const adapter = new PiEventAdapter(true);
  assert.deepEqual(
    adapter.feed({ type: "message_update", assistantMessageEvent: { type: "thinking_delta", delta: "x" } }),
    [{ type: "reasoning_start" }, { type: "reasoning_delta", text: "x" }],
  );
  assert.deepEqual(
    adapter.feed({ type: "message_update", assistantMessageEvent: { type: "text_delta", delta: "y" } }),
    [{ type: "reasoning_end" }, { type: "answer_delta", text: "y" }],
  );
});
