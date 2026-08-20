import path from "node:path";
import type { ExtensionFactory } from "@earendil-works/pi-coding-agent";
import {
  EXCALIDRAW_ELEMENTS_TOO_LARGE,
  INVALID_EXCALIDRAW_ELEMENTS,
  excalidrawElementsTooLarge,
  serializeExcalidrawElements,
} from "./mcp_app_registry.js";

const ANSWER_NOW =
  "Execution limit reached. Do not call more tools. Answer now from the evidence already gathered.";
const SEARCH = /(?:^|[;&|()\n]\s*)(?:pwc|s2)\s+search(?:\s|$)/iu;
const ANSI = /(?:\u001b\][^\u0007]*(?:\u0007|\u001b\\)|\u001b\[[0-?]*[ -/]*[@-~])/gu;
const GUIDES = new Set([
  "/opt/pwc/PWC_CLI_SKILL.md",
  "/opt/pwc/HF_CLI_SKILL.md",
  "/opt/pwc/S2_CLI_SKILL.md",
]);

function inside(candidate: string, root: string): boolean {
  const relative = path.relative(root, path.resolve(candidate));
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

function clean(value: string, maximum: number): { text: string; truncated: boolean } {
  const normalized = value
    .replace(ANSI, "")
    .split("")
    .filter((character) => character === "\n" || character === "\t" || character.charCodeAt(0) >= 32)
    .join("");
  const encoded = Buffer.from(normalized);
  if (encoded.length <= maximum) return { text: normalized, truncated: false };
  const hint = "\n[output truncated; narrow, filter, or paginate and try again]\n";
  if (maximum <= Buffer.byteLength(hint)) {
    return { text: Buffer.from(hint).subarray(0, maximum).toString("utf8"), truncated: true };
  }
  const prefix = encoded.subarray(0, Math.max(0, maximum - Buffer.byteLength(hint)));
  return { text: `${prefix.toString("utf8").replace(/\uFFFD$/u, "")}${hint}`, truncated: true };
}

export interface PolicyOptions {
  maximumCalls: number;
  maximumRounds: number;
  maximumDirectSearches: number;
  maximumWebSearches: number;
  maximumResultBytes: number;
  maximumTurnOutputBytes: number;
  bashTimeoutSeconds: number;
  excalidrawEnabled?: boolean;
}

export class PolicyController {
  webSearchEnabled = false;
  calls = 0;
  rounds = 0;
  searches = 0;
  webSearches = 0;
  readMeCalls = 0;
  createViewCalls = 0;
  outputBytes = 0;
  toolingClosed = false;
  answerProduced = false;
  answerAfterClose = false;
  systemPrompt = "";
  private active = new Set<string>();

  constructor(readonly options: PolicyOptions) {}

  reset(webSearchEnabled: boolean, systemPrompt = this.systemPrompt): void {
    this.webSearchEnabled = webSearchEnabled;
    this.systemPrompt = systemPrompt;
    this.calls = 0;
    this.rounds = 0;
    this.searches = 0;
    this.webSearches = 0;
    this.readMeCalls = 0;
    this.createViewCalls = 0;
    this.outputBytes = 0;
    this.toolingClosed = false;
    this.answerProduced = false;
    this.answerAfterClose = false;
    this.active.clear();
  }

  observeAnswer(): void {
    this.answerProduced = true;
    if (this.toolingClosed) this.answerAfterClose = true;
  }

  needsFinalAnswer(): boolean {
    return this.toolingClosed ? !this.answerAfterClose : !this.answerProduced;
  }

  private deny(id: string, reason: string): string {
    this.active.delete(id);
    return reason;
  }

  authorize(id: string, name: string, input: Record<string, unknown>): string | undefined {
    if (!this.active.size) this.rounds += 1;
    this.active.add(id);
    if (this.toolingClosed || this.rounds > this.options.maximumRounds || this.calls >= this.options.maximumCalls) {
      this.toolingClosed = true;
      return this.deny(id, ANSWER_NOW);
    }
    if (!new Set(["bash", "read", "search_web", "read_me", "create_view"]).has(name)) {
      return this.deny(id, "That tool is not available.");
    }
    if ((name === "read_me" || name === "create_view") && !this.options.excalidrawEnabled) {
      return this.deny(id, "Diagram tools are not available.");
    }
    if (name === "read_me") {
      if (this.readMeCalls >= 1) return this.deny(id, "read_me may be called once per turn.");
      this.readMeCalls += 1;
    }
    if (name === "create_view") {
      if (serializeExcalidrawElements(input.elements) === undefined) {
        return this.deny(
          id,
          excalidrawElementsTooLarge(input.elements)
            ? EXCALIDRAW_ELEMENTS_TOO_LARGE
            : INVALID_EXCALIDRAW_ELEMENTS,
        );
      }
      if (this.createViewCalls >= 2) return this.deny(id, "At most two diagrams may be created per turn.");
      this.createViewCalls += 1;
    }
    if (name === "read") {
      const requested = typeof input.path === "string" ? input.path : "";
      const resolved = path.resolve("/workspace", requested);
      if (!inside(resolved, "/workspace") && !GUIDES.has(resolved)) {
        return this.deny(id, "Read may only access /workspace or the approved CLI guides.");
      }
    }
    if (name === "bash") {
      const command = typeof input.command === "string" ? input.command : "";
      if (!command) return this.deny(id, "Invalid Bash command.");
      input.timeout = Math.min(
        this.options.bashTimeoutSeconds,
        typeof input.timeout === "number" ? input.timeout : this.options.bashTimeoutSeconds,
      );
      if (SEARCH.test(command)) {
        if (this.searches >= this.options.maximumDirectSearches) {
          this.toolingClosed = true;
          return this.deny(id, ANSWER_NOW);
        }
        this.searches += 1;
      }
    }
    if (name === "search_web") {
      const query = input.query;
      if (!this.webSearchEnabled || typeof query !== "string" || !query.trim() || query.length > 500) {
        return this.deny(id, "Web search is not available for this request.");
      }
      if (this.webSearches >= this.options.maximumWebSearches) {
        this.toolingClosed = true;
        return this.deny(id, ANSWER_NOW);
      }
      this.webSearches += 1;
    }
    this.calls += 1;
    return undefined;
  }

  finish(id: string, content: unknown): { content: Array<{ type: "text"; text: string }>; isError?: boolean } {
    this.active.delete(id);
    const raw = Array.isArray(content)
      ? content
          .map((part) =>
            part && typeof part === "object" && "text" in part ? String((part as { text: unknown }).text) : "",
          )
          .join("")
      : String(content ?? "");
    const remaining = Math.max(0, this.options.maximumTurnOutputBytes - this.outputBytes);
    const bounded = clean(raw, Math.min(remaining, this.options.maximumResultBytes));
    this.outputBytes += Buffer.byteLength(bounded.text);
    return {
      content: [{ type: "text", text: bounded.text }],
      ...(bounded.truncated ? { isError: false } : {}),
    };
  }
}

export function pwcExtension(policy: PolicyController): ExtensionFactory {
  return (pi) => {
    pi.on("before_agent_start", () => ({ systemPrompt: policy.systemPrompt }));
    pi.on("tool_call", (event) => {
      const reason = policy.authorize(event.toolCallId, event.toolName, event.input as Record<string, unknown>);
      return reason ? { block: true, reason } : undefined;
    });
    pi.on("tool_result", (event) => policy.finish(event.toolCallId, event.content));
  };
}

export { ANSWER_NOW };
