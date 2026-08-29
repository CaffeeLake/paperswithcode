import assert from "node:assert/strict";
import { once } from "node:events";
import test from "node:test";
import WebSocket from "ws";

import { createExternalWorkerServer } from "../src/external_server.js";
import { toolNameDigest } from "../src/mcp_app_registry.js";
import { parseAttachTurn, TurnProtocolError } from "../src/turn_protocol.js";

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
    expected_transcript_sha256: "04ec741c240dd09ab5ca2495141ac79893266747fd5c0bf966aa463e6fe69b5a",
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

test("external worker streams one authenticated Pi turn without a local shell", async () => {
  const token = "s".repeat(32);
  const observed: Record<string, unknown>[] = [];
  const server = createExternalWorkerServer({
    token,
    maximumConcurrent: 8,
    workerId: "worker-1",
    instanceId: "10000000-0000-4000-8000-000000000001",
    releaseId: "release-a",
    profile: { prompt: "system", tool_names: ["bash", "read"] },
    createTurnWorker: (emit, _run, channel) => ({
      async run(run) {
        observed.push(run as unknown as Record<string, unknown>);
        const tool = await channel.request({
          type: "tool_request", operation_id: "operation-1", tool_call_id: "tool-1",
          operation: "read", path: "/opt/pwc/PWC_CLI_SKILL.md", offset: 0,
          max_bytes: 1024,
        });
        assert.equal(tool.ok, true);
        emit(run.request_id, { type: "workspace_ready" });
        emit(run.request_id, { type: "done", finish_reason: "success", followups: [] });
        emit(run.request_id, { type: "worker_done", status: "complete" });
      },
      async cancel() {},
    }),
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  assert(address && typeof address === "object");
  const baseUrl = `http://127.0.0.1:${address.port}`;
  const claim = await fetch(`${baseUrl}/v1/claim`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ worker_generation: 3 }),
  });
  assert.equal(claim.status, 200);
  const socket = new WebSocket(`ws://127.0.0.1:${address.port}/v1/turn`, {
    headers: {
      Authorization: `Bearer ${token}`,
      "X-PWC-Worker-Generation": "3",
    },
  });
  const messages: Record<string, unknown>[] = [];
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(String(event.data)) as Record<string, unknown>;
    if (message.type === "tool_request") {
      socket.send(JSON.stringify({
        type: "tool_result", operation_id: message.operation_id, ok: true,
        data_base64: Buffer.from("guide").toString("base64"), eof: true,
      }));
      return;
    }
    messages.push(message);
  });
  try {
    await once(socket, "open");
    socket.send(JSON.stringify({
      v: 1,
      type: "run_turn",
      request_id: "request-1",
      chat_session_id: "10000000-0000-4000-8000-000000000001",
      turn_id: "20000000-0000-4000-8000-000000000001",
      turnClaim: {
        turnId: "20000000-0000-4000-8000-000000000001",
        workerId: "api-1",
        workerGeneration: 4,
        leaseGeneration: 9,
      },
      prompt: "Answer without tools.",
      model: "test-model",
      resume: null,
      web_search_enabled: false,
      reader_mode: false,
      poster_mode: false,
      paper_artifacts_enabled: false,
      reasoning_effort: "low",
      fetchable_urls: [],
      hf_username: "qualification",
      agent_harness: "pi",
      provider_protocol: "openai-responses",
      capability: "opaque-turn-capability",
      gateway_url: "https://gateway.example.test/api/internal/chat-gateway",
    }));
    while (!messages.some((message) => message.type === "worker_done")) {
      await once(socket, "message");
    }
    assert.deepEqual(messages.map((message) => message.type), [
      "workspace_ready", "done", "worker_done",
    ]);
    assert.equal(observed.length, 1);
    assert.equal(observed[0]?.capability, "opaque-turn-capability");
    assert.deepEqual(observed[0]?.turnClaim, {
      turnId: "20000000-0000-4000-8000-000000000001",
      workerId: "api-1",
      workerGeneration: 4,
      leaseGeneration: 9,
    });
  } finally {
    socket.close();
    server.close();
    await once(server, "close");
  }
});

test("external worker rejects missing and stale upgrade generations", async () => {
  const token = "s".repeat(32);
  const server = createExternalWorkerServer({
    token,
    maximumConcurrent: 8,
    workerId: "worker-1",
    instanceId: "10000000-0000-4000-8000-000000000001",
    releaseId: "release-a",
    profile: { prompt: "system", tool_names: [] },
    createTurnWorker: () => ({ async run() {}, async cancel() {} }),
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  assert(address && typeof address === "object");
  const baseUrl = `http://127.0.0.1:${address.port}`;
  await fetch(`${baseUrl}/v1/claim`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ worker_generation: 3 }),
  });

  const rejectedStatus = async (generation?: string): Promise<number> => {
    const socket = new WebSocket(`ws://127.0.0.1:${address.port}/v1/turn`, {
      headers: {
        Authorization: `Bearer ${token}`,
        ...(generation ? { "X-PWC-Worker-Generation": generation } : {}),
      },
    });
    const [, response] = await once(socket, "unexpected-response");
    return (response as { statusCode: number }).statusCode;
  };

  try {
    assert.equal(await rejectedStatus(), 409);
    assert.equal(await rejectedStatus("2"), 409);
  } finally {
    server.close();
    await once(server, "close");
  }
});

test("attach frame must carry the exact original turn claim", () => {
  const claim = {
    turnId: "20000000-0000-4000-8000-000000000001",
    workerId: "api-1",
    workerGeneration: 4,
    leaseGeneration: 9,
  };
  assert.deepEqual(parseAttachTurn({
    v: 1,
    type: "attach_turn",
    request_id: "request-1",
    turnClaim: claim,
    afterSequence: 12,
  }, claim).turnClaim, claim);
  assert.throws(() => parseAttachTurn({
    v: 1,
    type: "attach_turn",
    request_id: "request-1",
    turnClaim: { ...claim, leaseGeneration: 10 },
    afterSequence: 12,
  }, claim), TurnProtocolError);
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
      operation_counters: {
        shadow_requests: 0,
        model_calls: 0,
        tool_calls: 0,
        provider_calls: 0,
        modal_calls: 0,
        billing_events: 0,
      },
      capability_evidence: {
        provider_credentials_present: false,
        modal_credentials_present: false,
        registered_tool_count: 2,
      },
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

test("external worker status exposes observed content-free operation counters", async () => {
  const token = "s".repeat(32);
  const server = createExternalWorkerServer({
    token,
    maximumConcurrent: 8,
    workerId: "worker-1",
    instanceId: "10000000-0000-4000-8000-000000000001",
    releaseId: "release-a",
    profile: { prompt: "system", tool_names: [] },
    capabilityEvidence: {
      provider_credentials_present: false,
      modal_credentials_present: false,
    },
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  assert(address && typeof address === "object");
  const authorization = { Authorization: `Bearer ${token}` };
  try {
    await fetch(`http://127.0.0.1:${address.port}/v1/shadow`, {
      method: "POST", headers: authorization, body: "{}",
    });
    const status = await (await fetch(`http://127.0.0.1:${address.port}/v1/status`, {
      headers: authorization,
    })).json() as any;
    assert.equal(status.operation_counters.shadow_requests, 1);
    assert.deepEqual({ ...status.operation_counters, shadow_requests: 0 }, {
      shadow_requests: 0, model_calls: 0, tool_calls: 0, provider_calls: 0,
      modal_calls: 0, billing_events: 0,
    });
    assert.deepEqual(status.capability_evidence, {
      provider_credentials_present: false,
      modal_credentials_present: false,
      registered_tool_count: 0,
    });
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
