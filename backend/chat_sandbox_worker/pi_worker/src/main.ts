import readline from "node:readline";
import { PiWorker, type RunTurn } from "./agent.js";

const PREFIX = "@@PWC_CHAT_V1@@";
const MAX_FRAME_BYTES = 2 * 1024 * 1024 + 256 * 1024;
const persistent = process.env.PWC_CHAT_PERSISTENT_AGENT === "1";

function emit(requestId: string, event: Record<string, unknown>): void {
  const frame = JSON.stringify({ v: 1, request_id: requestId, ...event });
  if (Buffer.byteLength(frame) > MAX_FRAME_BYTES) throw new Error("Pi worker frame is too large");
  process.stdout.write(`${PREFIX}${frame}\n`);
}

function runFrame(value: unknown): RunTurn {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid Pi run frame");
  const frame = value as Record<string, unknown>;
  const required = new Set([
    "v", "type", "request_id", "chat_session_id", "prompt", "model", "resume",
    "web_search_enabled", "reasoning_effort", "fetchable_urls", "hf_username", "agent_harness",
  ]);
  const optional = new Set(["turn_id", "assignment_token", "worker_generation", "reader_mode"]);
  if (Object.keys(frame).some((key) => !required.has(key) && !optional.has(key))) throw new Error("Invalid Pi run frame keys");
  if ([...required].some((key) => !(key in frame))) throw new Error("Missing Pi run frame key");
  if (
    frame.v !== 1 || frame.type !== "run_turn" || frame.agent_harness !== "pi" ||
    typeof frame.request_id !== "string" || typeof frame.chat_session_id !== "string" ||
    typeof frame.prompt !== "string" || Buffer.byteLength(frame.prompt) > 2 * 1024 * 1024 ||
    typeof frame.model !== "string" ||
    (frame.resume !== null && typeof frame.resume !== "string") ||
    typeof frame.web_search_enabled !== "boolean" ||
    (frame.reader_mode !== undefined && typeof frame.reader_mode !== "boolean") ||
    !new Set(["low", "high", "max"]).has(String(frame.reasoning_effort)) ||
    typeof frame.hf_username !== "string" || !Array.isArray(frame.fetchable_urls)
  ) throw new Error("Invalid Pi run frame value");
  return { ...frame, reader_mode: frame.reader_mode === true } as unknown as RunTurn;
}

const worker = new PiWorker(emit);
const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
let chain = worker.initialize();

if (persistent) chain = chain.then(() => emit("startup", { type: "worker_ready" }));

input.on("line", (line) => {
  if (!line.startsWith(PREFIX) || Buffer.byteLength(line) > MAX_FRAME_BYTES + PREFIX.length) return;
  let decoded: Record<string, unknown>;
  try {
    decoded = JSON.parse(line.slice(PREFIX.length)) as Record<string, unknown>;
  } catch {
    return;
  }
  if (decoded.type === "cancel" && typeof decoded.request_id === "string") {
    void worker.cancel(decoded.request_id);
    return;
  }
  chain = chain
    .then(async () => {
      const requestId = typeof decoded.request_id === "string" ? decoded.request_id : "invalid";
      try {
        await worker.run(runFrame(decoded));
      } catch {
        emit(requestId, { type: "error", code: "invalid_request", message: "The research run failed." });
        emit(requestId, { type: "worker_done", status: "complete" });
      }
    })
    .finally(() => {
      if (!persistent) input.close();
    });
});

input.on("close", () => {
  void chain.finally(() => {
    process.exitCode = 0;
  });
});
