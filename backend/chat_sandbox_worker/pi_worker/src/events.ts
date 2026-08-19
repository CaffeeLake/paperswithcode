export type PwCEvent = Record<string, unknown> & { type: string };

type UnknownRecord = Record<string, unknown>;

function record(value: unknown): UnknownRecord {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as UnknownRecord)
    : {};
}

function textContent(value: unknown): string {
  if (typeof value === "string") return value;
  if (!Array.isArray(value)) return JSON.stringify(value ?? null);
  return value
    .map((item) => {
      const part = record(item);
      return part.type === "text" && typeof part.text === "string" ? part.text : "";
    })
    .join("");
}

function publicToolName(value: unknown): string {
  const name = String(value ?? "");
  if (name === "bash") return "Bash";
  if (name === "read") return "Read";
  return name;
}

function excalidrawElements(value: unknown): string | undefined {
  const elements = record(value).elements;
  const serialized = typeof elements === "string" ? elements : JSON.stringify(elements ?? null);
  if (Buffer.byteLength(serialized) > 128 * 1024) return undefined;
  try {
    if (!Array.isArray(JSON.parse(serialized))) return undefined;
  } catch {
    return undefined;
  }
  return serialized;
}

export function reasoningIsVisible(value: string | undefined): boolean {
  return value === "true";
}

export class PiEventAdapter {
  private reasoningOpen = false;
  private answerStarted = false;
  private terminalFailure = false;
  private readonly toolIds = new Set<string>();
  private readonly resultIds = new Set<string>();
  private readonly toolStartedAt = new Map<string, number>();
  private readonly toolNames = new Map<string, string>();

  constructor(
    private readonly showReasoning: boolean,
    private readonly onSemantic?: (kind: "reasoning" | "tool" | "answer") => void,
    private readonly now: () => number = () => performance.now(),
  ) {}

  get failed(): boolean {
    return this.terminalFailure;
  }

  private closeReasoning(): PwCEvent[] {
    if (!this.reasoningOpen) return [];
    this.reasoningOpen = false;
    return this.showReasoning ? [{ type: "reasoning_end" }] : [];
  }

  feed(rawEvent: unknown): PwCEvent[] {
    const event = record(rawEvent);
    const type = event.type;
    if (type === "message_update") {
      const update = record(event.assistantMessageEvent);
      if (update.type === "thinking_delta") {
        this.onSemantic?.("reasoning");
        if (!this.showReasoning) return [];
        const output: PwCEvent[] = [];
        if (!this.reasoningOpen) {
          this.reasoningOpen = true;
          output.push({ type: "reasoning_start" });
        }
        if (typeof update.delta === "string" && update.delta) {
          output.push({ type: "reasoning_delta", text: update.delta });
        }
        return output;
      }
      if (update.type === "text_delta" && typeof update.delta === "string") {
        const output = this.closeReasoning();
        if (update.delta && (this.answerStarted || update.delta.trim())) {
          this.answerStarted = true;
          this.onSemantic?.("answer");
          output.push({ type: "answer_delta", text: update.delta });
        }
        return output;
      }
      return [];
    }
    if (type === "tool_execution_start") {
      const id = typeof event.toolCallId === "string" ? event.toolCallId : "";
      if (!id || this.toolIds.has(id)) return [];
      const args = record(event.args);
      const name = String(event.toolName ?? "");
      if (name === "create_view") {
        const elements = excalidrawElements(args);
        if (!elements) return [];
        this.toolIds.add(id);
        this.toolNames.set(id, name);
        this.toolStartedAt.set(id, this.now());
        this.onSemantic?.("tool");
        return [
          ...this.closeReasoning(),
          {
            type: "app_start",
            id,
            instance_id: id,
            provider: "excalidraw",
            server: "excalidraw",
            tool: "create_view",
            resource_uri: "ui://excalidraw/mcp-app.html",
            input: { elements },
          },
        ];
      }
      this.toolIds.add(id);
      this.toolNames.set(id, name);
      this.toolStartedAt.set(id, this.now());
      this.onSemantic?.("tool");
      return [
        ...this.closeReasoning(),
        {
          type: "tool_call",
          id,
          name: publicToolName(event.toolName),
          args,
        },
      ];
    }
    if (type === "tool_execution_end") {
      const id = typeof event.toolCallId === "string" ? event.toolCallId : "";
      if (!this.toolIds.has(id) || this.resultIds.has(id)) return [];
      this.resultIds.add(id);
      const startedAt = this.toolStartedAt.get(id);
      this.toolStartedAt.delete(id);
      const toolName = this.toolNames.get(id);
      this.toolNames.delete(id);
      const result = record(event.result);
      const content = textContent(result.content ?? event.result);
      if (toolName === "create_view") {
        const checkpoint = record(result.structuredContent).checkpointId;
        return [{
          type: "app_result",
          id,
          status: event.isError ? "error" : "ready",
          took_ms: startedAt === undefined ? 0 : Math.max(0, Math.round(this.now() - startedAt)),
          result: {
            content: [{ type: "text", text: content.slice(0, 8_192), truncated: Buffer.byteLength(content) > 8_192 }],
            structuredContent: typeof checkpoint === "string" && checkpoint.length <= 512 ? { checkpointId: checkpoint } : {},
            isError: event.isError === true,
          },
        }];
      }
      return [
        {
          type: "tool_result",
          id,
          status: event.isError ? "error" : "success",
          took_ms: startedAt === undefined ? 0 : Math.max(0, Math.round(this.now() - startedAt)),
          content: [{ type: "text", text: content, truncated: false }],
          metadata: { output_truncated: false },
        },
      ];
    }
    if (type === "message_end") {
      const message = record(event.message);
      if (message.role !== "assistant") return [];
      if (message.stopReason === "error" || typeof message.errorMessage === "string") {
        this.terminalFailure = true;
        return [
          ...this.closeReasoning(),
          {
            type: "error",
            code: "provider_error",
            message: "The model provider is unavailable.",
          },
        ];
      }
      const usage = record(message.usage);
      return [
        {
          type: "usage",
          usage,
          model_usage: {},
          total_cost_usd: record(usage.cost).total ?? 0,
          provider_requests: 1,
        },
      ];
    }
    if (type === "agent_settled") return this.closeReasoning();
    return [];
  }
}
