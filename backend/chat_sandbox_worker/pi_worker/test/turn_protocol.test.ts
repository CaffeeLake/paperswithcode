import assert from "node:assert/strict";
import test from "node:test";

import { parseAttachTurn } from "../src/turn_protocol.js";

test("preserves canonical int64 turn generations without JavaScript precision loss", () => {
  const claim = {
    turnId: "turn-1",
    workerId: "local-runner:opaque",
    workerGeneration: "8551922832508112075",
    leaseGeneration: "9",
  };

  assert.deepEqual(
    parseAttachTurn({
      v: 1,
      type: "attach_turn",
      request_id: "request-1",
      turnClaim: claim,
      afterSequence: 1,
    }).turnClaim,
    claim,
  );
});
