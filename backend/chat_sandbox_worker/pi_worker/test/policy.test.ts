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
