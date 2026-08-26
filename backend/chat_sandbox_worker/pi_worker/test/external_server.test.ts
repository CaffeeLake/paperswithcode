import assert from "node:assert/strict";
import { once } from "node:events";
import test from "node:test";

import { createExternalWorkerServer } from "../src/external_server.js";
import { toolNameDigest } from "../src/mcp_app_registry.js";

test("external shadow HTTP service authenticates and exposes no run endpoint", async () => {
  const server = createExternalWorkerServer({
    token: "s".repeat(32),
    maximumConcurrent: 8,
    workerId: "worker-1",
    instanceId: "10000000-0000-4000-8000-000000000001",
    releaseId: "release-a",
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

test("external worker status is authenticated and drain blocks new sessions", async () => {
  const token = "s".repeat(32);
  const server = createExternalWorkerServer({
    token,
    maximumConcurrent: 8,
    workerId: "worker-1",
    instanceId: "10000000-0000-4000-8000-000000000001",
    releaseId: "release-a",
    profile: { prompt: "system", tool_names: ["bash", "read"] },
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  assert(address && typeof address === "object");
  const baseUrl = `http://127.0.0.1:${address.port}`;
  const authorization = { Authorization: `Bearer ${token}` };
  try {
    assert.equal((await fetch(`${baseUrl}/v1/status`)).status, 401);
    const ready = await (await fetch(`${baseUrl}/v1/status`, {
      headers: authorization,
    })).json() as Record<string, unknown>;
    assert.deepEqual(ready, {
      protocol: "external-pi-v1",
      worker_id: "worker-1",
      instance_id: "10000000-0000-4000-8000-000000000001",
      release_id: "release-a",
      state: "ready",
      active_sessions: 0,
      maximum_sessions: 8,
      worker_generation: null,
    });

    const claim = await fetch(`${baseUrl}/v1/claim`, {
      method: "POST",
      headers: { ...authorization, "Content-Type": "application/json" },
      body: JSON.stringify({ worker_generation: 3 }),
    });
    assert.equal(claim.status, 200);
    assert.equal((await claim.json() as { worker_generation: number }).worker_generation, 3);

    assert.equal((await fetch(`${baseUrl}/v1/drain`, {
      method: "POST",
      headers: { ...authorization, "X-PWC-Worker-Generation": "2" },
    })).status, 409);
    const drain = await fetch(`${baseUrl}/v1/drain`, {
      method: "POST",
      headers: { ...authorization, "X-PWC-Worker-Generation": "3" },
    });
    assert.equal(drain.status, 200);
    assert.equal((await drain.json() as { state: string }).state, "draining");

    const shadow = await fetch(`${baseUrl}/v1/shadow`, {
      method: "POST",
      headers: authorization,
    });
    assert.equal(shadow.status, 503);
    assert.deepEqual(await shadow.json(), { code: "worker_draining" });
  } finally {
    server.close();
    await once(server, "close");
  }
});

test("external worker capacity remains configurable above the initial eight", () => {
  const options = {
    token: "s".repeat(32),
    maximumConcurrent: 32,
    workerId: "worker-1",
    instanceId: "10000000-0000-4000-8000-000000000001",
    releaseId: "release-a",
    profile: { prompt: "system", tool_names: ["bash", "read"] },
  };
  assert.doesNotThrow(() => createExternalWorkerServer(options));
  assert.throws(
    () => createExternalWorkerServer({ ...options, maximumConcurrent: 33 }),
    /concurrency is invalid/,
  );
});
