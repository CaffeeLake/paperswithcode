import assert from "node:assert/strict";
import test from "node:test";

import { turnFailureDiagnostic } from "../src/agent.js";

test("turn failure diagnostic exposes only the bounded phase and error class", () => {
  const diagnostic = turnFailureDiagnostic(
    "session_bind_restore",
    new TypeError("secret prompt and capability must not be logged"),
  );

  assert.equal(
    diagnostic,
    "External Pi turn failed phase=session_bind_restore error=TypeError\n",
  );
  assert.doesNotMatch(diagnostic, /secret|prompt|capability/u);
});
