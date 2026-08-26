import assert from "node:assert/strict";
import test from "node:test";

import {
  compareShadowState,
  projectShadowState,
  type ExternalShadowRequest,
} from "../src/external_shadow.js";
import { handleExternalFrame } from "../src/external_worker.js";

const request: ExternalShadowRequest = {
  protocol_version: 1,
  request_id: "shadow-1",
  chat_session_id: "10000000-0000-4000-8000-000000000001",
  agent_session_id: "20000000-0000-4000-8000-000000000001",
  current_leaf_id: "entry-1",
  expected_prompt_sha256: "caebbfd4c48e98a97a0c0162ac34efec70d452e823114c2f882d586934169454",
  expected_tool_names_sha256: "654bf373a312fb2825c0afbc75ce871cad185cacdbdf10ca3dd4875efddf3b65",
  transcript_entries: [
    {
      type: "session",
      id: "20000000-0000-4000-8000-000000000001",
      version: 3,
    },
    { type: "message", id: "entry-1", parentId: null, role: "user" },
  ],
};

const profile = {
  prompt: "trusted system prompt",
  tool_names: ["read", "bash", "pwc__search"],
};

test("external shadow projection is content-free and stable", () => {
  const projection = projectShadowState(request, profile);

  assert.deepEqual(projection, {
    protocol_version: 1,
    request_id: "shadow-1",
    chat_session_id: "10000000-0000-4000-8000-000000000001",
    agent_session_id: "20000000-0000-4000-8000-000000000001",
    current_leaf_id: "entry-1",
    entry_count: 2,
    prompt_sha256: "caebbfd4c48e98a97a0c0162ac34efec70d452e823114c2f882d586934169454",
    tool_names_sha256: "654bf373a312fb2825c0afbc75ce871cad185cacdbdf10ca3dd4875efddf3b65",
  });
  assert.doesNotMatch(JSON.stringify(projection), /trusted system prompt|role/);
});

test("external worker shadow endpoint cannot dispatch model or tool work", () => {
  assert.deepEqual(
    handleExternalFrame({ type: "shadow_compare", ...request }, profile),
    { type: "shadow_projection", ...projectShadowState(request, profile) },
  );
  assert.throws(
    () => handleExternalFrame({ type: "run_turn", ...request }, profile),
    /shadow_compare/,
  );
  assert.throws(
    () => handleExternalFrame({ type: "shadow_compare", ...request, provider_token: "secret" }, profile),
    /keys/,
  );
});

test("external shadow rejects a transcript whose durable leaf is absent", () => {
  assert.throws(
    () => projectShadowState({ ...request, current_leaf_id: "missing" }, profile),
    /current leaf/i,
  );
});

test("external shadow comparison reports exact compatibility fields", () => {
  const projection = projectShadowState(request, profile);

  assert.deepEqual(compareShadowState(projection, projection), {
    compatible: true,
    mismatches: [],
  });
  assert.deepEqual(
    compareShadowState(projection, { ...projection, tool_names_sha256: "0".repeat(64) }),
    { compatible: false, mismatches: ["tool_names_sha256"] },
  );
});
