import { type RunTurn } from "./agent.js";

export const MAX_TURN_FRAME_BYTES = 2 * 1024 * 1024 + 256 * 1024;

export interface ExternalRunTurn extends RunTurn {
  turn_id: string;
  turnClaim: TurnClaimFrame;
  capability: string;
  gateway_url: string;
}

export interface TurnClaimFrame {
  turnId: string;
  workerId: string;
  workerGeneration: number;
  leaseGeneration: number;
}

export interface AttachTurn {
  v: 1;
  type: "attach_turn";
  request_id: string;
  turnClaim: TurnClaimFrame;
  afterSequence: number;
}

export class TurnProtocolError extends Error {}

function parseTurnClaim(value: unknown): TurnClaimFrame {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new TurnProtocolError("Invalid Pi turn claim");
  }
  const claim = value as Record<string, unknown>;
  if (
    Object.keys(claim).length !== 4
    || typeof claim.turnId !== "string"
    || !claim.turnId
    || typeof claim.workerId !== "string"
    || !claim.workerId
    || !Number.isSafeInteger(claim.workerGeneration)
    || (claim.workerGeneration as number) < 1
    || !Number.isSafeInteger(claim.leaseGeneration)
    || (claim.leaseGeneration as number) < 1
  ) {
    throw new TurnProtocolError("Invalid Pi turn claim");
  }
  return claim as unknown as TurnClaimFrame;
}

function claimsEqual(left: TurnClaimFrame, right: TurnClaimFrame): boolean {
  return left.turnId === right.turnId
    && left.workerId === right.workerId
    && left.workerGeneration === right.workerGeneration
    && left.leaseGeneration === right.leaseGeneration;
}

export function parseAttachTurn(
  value: unknown,
  expectedClaim: TurnClaimFrame,
): AttachTurn {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new TurnProtocolError("Invalid Pi attach frame");
  }
  const frame = value as Record<string, unknown>;
  if (
    Object.keys(frame).length !== 5
    || frame.v !== 1
    || frame.type !== "attach_turn"
    || typeof frame.request_id !== "string"
    || !frame.request_id
    || !Number.isSafeInteger(frame.afterSequence)
    || (frame.afterSequence as number) < 0
  ) {
    throw new TurnProtocolError("Invalid Pi attach frame");
  }
  const turnClaim = parseTurnClaim(frame.turnClaim);
  if (!claimsEqual(turnClaim, expectedClaim)) {
    throw new TurnProtocolError("Stale Pi turn claim");
  }
  return { ...frame, turnClaim } as unknown as AttachTurn;
}

export function parseRunTurn(value: unknown, external = false): RunTurn | ExternalRunTurn {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new TurnProtocolError("Invalid Pi run frame");
  }
  const frame = value as Record<string, unknown>;
  const required = new Set([
    "v", "type", "request_id", "chat_session_id", "prompt", "model", "resume",
    "web_search_enabled", "reasoning_effort", "fetchable_urls", "hf_username", "agent_harness",
  ]);
  if (external) {
    required.add("turn_id");
    required.add("turnClaim");
    required.add("capability");
    required.add("gateway_url");
  }
  const optional = new Set([
    "turn_id", "assignment_token", "worker_generation", "reader_mode", "poster_mode",
    "paper_artifacts_enabled", "paper_descriptor", "provider_protocol",
  ]);
  if (Object.keys(frame).some((key) => !required.has(key) && !optional.has(key))) {
    throw new TurnProtocolError("Invalid Pi run frame keys");
  }
  if ([...required].some((key) => !(key in frame))) throw new TurnProtocolError("Missing Pi run frame key");
  const turnClaim = external ? parseTurnClaim(frame.turnClaim) : undefined;
  if (
    frame.v !== 1 || frame.type !== "run_turn" || frame.agent_harness !== "pi" ||
    typeof frame.request_id !== "string" || typeof frame.chat_session_id !== "string" ||
    typeof frame.prompt !== "string" || Buffer.byteLength(frame.prompt) > 2 * 1024 * 1024 ||
    typeof frame.model !== "string" ||
    (frame.provider_protocol !== undefined
      && !new Set(["anthropic-messages", "openai-responses"]).has(String(frame.provider_protocol))) ||
    (frame.resume !== null && typeof frame.resume !== "string") ||
    typeof frame.web_search_enabled !== "boolean" ||
    (frame.reader_mode !== undefined && typeof frame.reader_mode !== "boolean") ||
    (frame.poster_mode !== undefined && typeof frame.poster_mode !== "boolean") ||
    (frame.paper_artifacts_enabled !== undefined && typeof frame.paper_artifacts_enabled !== "boolean") ||
    (frame.paper_descriptor !== undefined && (!frame.paper_descriptor || typeof frame.paper_descriptor !== "object" || Array.isArray(frame.paper_descriptor))) ||
    !new Set(["low", "high", "max"]).has(String(frame.reasoning_effort)) ||
    typeof frame.hf_username !== "string" || !Array.isArray(frame.fetchable_urls) ||
    (external && (
      typeof frame.turn_id !== "string" || !frame.turn_id ||
      turnClaim?.turnId !== frame.turn_id ||
      typeof frame.capability !== "string" || !frame.capability ||
      typeof frame.gateway_url !== "string" || !frame.gateway_url.startsWith("https://")
    ))
  ) throw new TurnProtocolError("Invalid Pi run frame value");
  return {
    ...frame,
    reader_mode: frame.reader_mode === true,
    poster_mode: frame.poster_mode === true,
    paper_artifacts_enabled: frame.paper_artifacts_enabled === true,
  } as unknown as RunTurn | ExternalRunTurn;
}
