import assert from "node:assert/strict";
import test from "node:test";

import { shouldResetSession } from "../src/session.js";

test("warm state resets for both fork and blank-transcript activation", () => {
  assert.equal(shouldResetSession("old-session", "fork-session"), true);
  assert.equal(shouldResetSession("old-session", null), true);
  assert.equal(shouldResetSession("old-session", "old-session"), false);
  assert.equal(shouldResetSession(undefined, null), false);
});
