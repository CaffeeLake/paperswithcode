import { createHash, timingSafeEqual } from "node:crypto";
import http, { type IncomingMessage, type ServerResponse } from "node:http";

import { handleExternalFrame, MAX_EXTERNAL_FRAME_BYTES } from "./external_worker.js";
import { type ExternalWorkerProfile } from "./external_shadow.js";

interface ExternalWorkerServerOptions {
  token: string;
  maximumConcurrent: number;
  workerId: string;
  instanceId: string;
  releaseId: string;
  profile: ExternalWorkerProfile;
}

function tokenDigest(value: string): Buffer {
  return createHash("sha256").update(value, "utf8").digest();
}

function authorized(request: IncomingMessage, expected: Buffer): boolean {
  const authorization = request.headers.authorization ?? "";
  const [scheme, token, extra] = authorization.split(" ");
  return scheme === "Bearer"
    && typeof token === "string"
    && extra === undefined
    && timingSafeEqual(tokenDigest(token), expected);
}

function json(response: ServerResponse, status: number, payload: object): void {
  const body = JSON.stringify(payload);
  response.writeHead(status, {
    "Content-Type": "application/json",
    "Content-Length": Buffer.byteLength(body),
    "Cache-Control": "no-store",
  });
  response.end(body);
}

async function readBody(request: IncomingMessage): Promise<Buffer> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of request) {
    const bytes = Buffer.from(chunk);
    size += bytes.length;
    if (size > MAX_EXTERNAL_FRAME_BYTES) throw new Error("request_too_large");
    chunks.push(bytes);
  }
  return Buffer.concat(chunks, size);
}

export function createExternalWorkerServer(options: ExternalWorkerServerOptions): http.Server {
  if (options.token.length < 32) throw new Error("External worker token is too short");
  if (!Number.isInteger(options.maximumConcurrent) || options.maximumConcurrent < 1 || options.maximumConcurrent > 32) {
    throw new Error("External worker concurrency is invalid");
  }
  if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(options.workerId)) {
    throw new Error("External worker identity is invalid");
  }
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(options.instanceId)) {
    throw new Error("External worker instance is invalid");
  }
  if (!options.releaseId || options.releaseId.length > 255) {
    throw new Error("External worker release is invalid");
  }
  const expectedToken = tokenDigest(options.token);
  const requireAuthorization = (
    request: IncomingMessage,
    response: ServerResponse,
  ): boolean => {
    if (authorized(request, expectedToken)) return true;
    json(response, 401, { code: "unauthorized" });
    return false;
  };
  let active = 0;
  let state: "ready" | "draining" = "ready";
  let workerGeneration: number | null = null;
  const status = () => ({
    protocol: "external-pi-v1",
    worker_id: options.workerId,
    instance_id: options.instanceId,
    release_id: options.releaseId,
    state,
    active_sessions: active,
    maximum_sessions: options.maximumConcurrent,
    worker_generation: workerGeneration,
  });
  return http.createServer(async (request, response) => {
    if (request.method === "GET" && request.url === "/health") {
      json(response, 200, {
        status: "ok",
        mode: "shadow",
        protocol: "external-pi-v1",
        active,
        capacity: options.maximumConcurrent,
      });
      return;
    }
    if (request.method === "GET" && request.url === "/v1/status") {
      if (!requireAuthorization(request, response)) return;
      json(response, 200, status());
      return;
    }
    if (request.method === "POST" && request.url === "/v1/claim") {
      if (!requireAuthorization(request, response)) return;
      try {
        const value = JSON.parse((await readBody(request)).toString("utf8")) as unknown;
        if (
          !value
          || typeof value !== "object"
          || Array.isArray(value)
          || Object.keys(value).length !== 1
          || !("worker_generation" in value)
          || !Number.isSafeInteger(value.worker_generation)
          || (value.worker_generation as number) < 1
          || (workerGeneration !== null && (value.worker_generation as number) < workerGeneration)
        ) {
          throw new Error("invalid_worker_generation");
        }
        workerGeneration = value.worker_generation as number;
        json(response, 200, status());
      } catch {
        json(response, 400, { code: "invalid_worker_claim" });
      }
      return;
    }
    if (request.method === "POST" && request.url === "/v1/drain") {
      if (!requireAuthorization(request, response)) return;
      if (
        workerGeneration === null
        || request.headers["x-pwc-worker-generation"] !== String(workerGeneration)
      ) {
        json(response, 409, { code: "stale_worker_generation" });
        return;
      }
      state = "draining";
      json(response, 200, status());
      return;
    }
    if (request.method !== "POST" || request.url !== "/v1/shadow") {
      json(response, 404, { code: "not_found" });
      return;
    }
    if (!requireAuthorization(request, response)) return;
    if (state === "draining") {
      json(response, 503, { code: "worker_draining" });
      return;
    }
    if (active >= options.maximumConcurrent) {
      json(response, 503, { code: "shadow_capacity" });
      return;
    }
    active += 1;
    try {
      const body = await readBody(request);
      json(
        response,
        200,
        await handleExternalFrame(
          JSON.parse(body.toString("utf8")) as unknown,
          options.profile,
        ),
      );
    } catch (error) {
      const status = error instanceof Error && error.message === "request_too_large" ? 413 : 400;
      json(response, status, { code: "invalid_shadow_request" });
    } finally {
      active -= 1;
    }
  });
}
