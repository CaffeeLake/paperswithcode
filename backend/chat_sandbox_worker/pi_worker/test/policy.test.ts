import assert from "node:assert/strict";
import test from "node:test";
import { PolicyController } from "../src/policy.js";

function policy(): PolicyController {
  return new PolicyController({
    maximumCalls: 3,
    maximumRounds: 2,
    maximumDirectSearches: 1,
    maximumWebSearches: 1,
    maximumResultBytes: 12,
    maximumTurnOutputBytes: 20,
    bashTimeoutSeconds: 5,
  });
}

test("enforces tool, path, search, timeout, and output bounds", () => {
  const value = policy();
  value.reset(true, "prompt");
  const bash: Record<string, unknown> = { command: "pwc search test", timeout: 99 };
  assert.equal(value.authorize("a", "bash", bash), undefined);
  assert.equal(bash.timeout, 5);
  assert.match(value.authorize("b", "bash", { command: "pwc search again" }) ?? "", /answer now/iu);
  value.finish("a", "\u001b[31mabcdefghijklmnop");
  assert.ok(value.outputBytes <= 20);

  const scoped = policy();
  scoped.reset(false);
  assert.match(scoped.authorize("r", "read", { path: "/etc/passwd" }) ?? "", /only access/iu);
  const noWeb = policy();
  noWeb.reset(false);
  assert.match(noWeb.authorize("w", "search_web", { query: "current papers" }) ?? "", /not available/iu);
  const noWrite = policy();
  noWrite.reset(false);
  assert.match(noWrite.authorize("x", "write", {}) ?? "", /not available/iu);
});

test("counts s2 search against the shared catalog search limit", () => {
  const value = policy();
  value.reset(false);
  assert.equal(value.authorize("a", "bash", { command: "s2 search transformers" }), undefined);
  assert.match(
    value.authorize("b", "bash", { command: "pwc search transformers" }) ?? "",
    /answer now/iu,
  );
});

test("rejects invalid create_view JSON without consuming the diagram budget", () => {
  const value = new PolicyController({
    maximumCalls: 4,
    maximumRounds: 4,
    maximumDirectSearches: 1,
    maximumWebSearches: 1,
    maximumResultBytes: 1024,
    maximumTurnOutputBytes: 4096,
    bashTimeoutSeconds: 5,
    excalidrawEnabled: true,
  });
  value.reset(false);
  assert.match(
    value.authorize("bad", "create_view", {
      elements: '[{"type":"arrow","label":{"text":"draft tokens"}}},]',
    }) ?? "",
    /JSON array/u,
  );
  assert.equal(value.createViewCalls, 0);
  assert.equal(
    value.authorize("ok", "create_view", { elements: [{ type: "rectangle", id: "n1" }] }),
    undefined,
  );
  assert.equal(value.createViewCalls, 1);
});

test("requires a visible answer, including after tooling closes", () => {
  const value = policy();
  value.reset(false);
  assert.equal(value.needsFinalAnswer(), true);
  value.observeAnswer();
  assert.equal(value.needsFinalAnswer(), false);

  assert.equal(value.authorize("a", "bash", { command: "pwc search test" }), undefined);
  assert.match(value.authorize("b", "bash", { command: "pwc search again" }) ?? "", /answer now/iu);
  assert.equal(value.needsFinalAnswer(), true);
  value.observeAnswer();
  assert.equal(value.needsFinalAnswer(), false);
});
