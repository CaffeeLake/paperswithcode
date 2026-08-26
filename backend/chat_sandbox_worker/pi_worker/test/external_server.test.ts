import assert from "node:assert/strict";
import { once } from "node:events";
import test from "node:test";

import { createExternalShadowServer } from "../src/external_server.js";
import { toolNameDigest } from "../src/mcp_app_registry.js";

test("external shadow HTTP service authenticates and exposes no run endpoint", async () => {
  const server = createExternalShadowServer({
    token: "s".repeat(32),
    maximumConcurrent: 8,
    profile: { prompt: "system", tool_names: ["bash", "read"] },
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  assert(address && typeof address === "object");
  const baseUrl = `http://127.0.0.1:${address.port}`;
  const payload = {
    type: "shadow_compare",
    protocol_version: 1,
    request_id: "shadow-1",
    chat_session_id: "10000000-0000-4000-8000-000000000001",
    agent_session_id: "20000000-0000-4000-8000-000000000001",
    current_leaf_id: null,
    expected_prompt_sha256: "bbc5e661e106c6dcd8dc6dd186454c2fcba3c710fb4d8e71a60c93eaf077f073",
    expected_tool_names_sha256: toolNameDigest(["bash", "read"]),
    transcript_entries: [{
      type: "session", id: "20000000-0000-4000-8000-000000000001", version: 3,
    }],
  };
  try {
    assert.equal((await fetch(`${baseUrl}/health`)).status, 200);
    assert.equal((await fetch(`${baseUrl}/v1/shadow`, { method: "POST" })).status, 401);
    assert.equal((await fetch(`${baseUrl}/v1/run`, {
      method: "POST",
      headers: { Authorization: `Bearer ${"s".repeat(32)}` },
    })).status, 404);
    const response = await fetch(`${baseUrl}/v1/shadow`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${"s".repeat(32)}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
    assert.equal(response.status, 200);
    const projection = await response.json() as {
      type: string; prompt_sha256: string; tool_names_sha256: string;
    };
    assert.equal(projection.type, "shadow_projection");
    assert.equal(projection.prompt_sha256, payload.expected_prompt_sha256);
    assert.equal(projection.tool_names_sha256, payload.expected_tool_names_sha256);
  } finally {
    server.close();
    await once(server, "close");
  }
});
