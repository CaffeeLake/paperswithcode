import { createHash, timingSafeEqual } from "node:crypto";
import http, { type IncomingMessage, type ServerResponse } from "node:http";

import { handleExternalFrame, MAX_EXTERNAL_FRAME_BYTES } from "./external_worker.js";
import { type ExternalWorkerProfile } from "./external_shadow.js";

interface ExternalShadowServerOptions {
  token: string;
  maximumConcurrent: number;
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

export function createExternalShadowServer(options: ExternalShadowServerOptions): http.Server {
  if (options.token.length < 32) throw new Error("External worker token is too short");
  if (!Number.isInteger(options.maximumConcurrent) || options.maximumConcurrent < 1 || options.maximumConcurrent > 32) {
    throw new Error("External worker concurrency is invalid");
  }
  const expectedToken = tokenDigest(options.token);
  let active = 0;
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
    if (request.method !== "POST" || request.url !== "/v1/shadow") {
      json(response, 404, { code: "not_found" });
      return;
    }
    if (!authorized(request, expectedToken)) {
      json(response, 401, { code: "unauthorized" });
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
        handleExternalFrame(JSON.parse(body.toString("utf8")) as unknown, options.profile),
      );
    } catch (error) {
      const status = error instanceof Error && error.message === "request_too_large" ? 413 : 400;
      json(response, status, { code: "invalid_shadow_request" });
    } finally {
      active -= 1;
    }
  });
}
