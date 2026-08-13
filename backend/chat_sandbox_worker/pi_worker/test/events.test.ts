import assert from "node:assert/strict";
import test from "node:test";
import { PiEventAdapter } from "../src/events.js";
import { PolicyController } from "../src/policy.js";

function policy(): PolicyController {
  return new PolicyController({
    maximumCalls: 3,
    maximumRounds: 2,
    maximumDirectSearches: 1,
    maximumWebSearches: 1,
    maximumResultBytes: 1024,
    maximumTurnOutputBytes: 4096,
    bashTimeoutSeconds: 5,
  });
}

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

test("measures each tool from execution start to end", () => {
  let now = 100;
  const adapter = new PiEventAdapter(false, undefined, () => now);
  adapter.feed({ type: "tool_execution_start", toolCallId: "slow", toolName: "bash", args: {} });
  now = 125.4;
  adapter.feed({ type: "tool_execution_start", toolCallId: "fast", toolName: "read", args: {} });
  now = 138.8;
  assert.equal(
    adapter.feed({ type: "tool_execution_end", toolCallId: "fast", result: {}, isError: false })[0]?.took_ms,
    13,
  );
  now = 161.6;
  assert.equal(
    adapter.feed({ type: "tool_execution_end", toolCallId: "slow", result: {}, isError: false })[0]?.took_ms,
    62,
  );
});

test("surfaces terminal provider errors without exposing provider details", () => {
  const adapter = new PiEventAdapter(false);
  assert.deepEqual(
    adapter.feed({
      type: "message_end",
      message: {
        role: "assistant",
        stopReason: "error",
        errorMessage: "sensitive upstream response",
        content: [],
      },
    }),
    [
      {
        type: "error",
        code: "provider_error",
        message: "The model provider is unavailable.",
      },
    ],
  );
  assert.equal(adapter.failed, true);
});

test("reasoning-only tool markup requires a final answer", () => {
  const completion = policy();
  completion.reset(false);
  const adapter = new PiEventAdapter(false, (kind) => {
    if (kind === "answer") completion.observeAnswer();
  });

  assert.deepEqual(
    adapter.feed({
      type: "message_update",
      assistantMessageEvent: {
        type: "thinking_delta",
        delta: "<｜DSML｜tool_calls>pwc paper info Patch Policy</｜DSML｜tool_calls>",
      },
    }),
    [],
  );
  adapter.feed({
    type: "message_end",
    message: { role: "assistant", stopReason: "stop", usage: {} },
  });
  assert.equal(completion.needsFinalAnswer(), true);

  adapter.feed({
    type: "message_update",
    assistantMessageEvent: { type: "text_delta", delta: "Recovered answer" },
  });
  assert.equal(completion.needsFinalAnswer(), false);
});
