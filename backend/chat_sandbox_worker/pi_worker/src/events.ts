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

export class PiEventAdapter {
  private reasoningOpen = false;
  private answerStarted = false;
  private readonly toolIds = new Set<string>();
  private readonly resultIds = new Set<string>();

  constructor(
    private readonly showReasoning: boolean,
    private readonly onSemantic?: (kind: "reasoning" | "tool" | "answer") => void,
  ) {}

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
      if (!id || this.toolIds.has(id)) throw new Error("invalid Pi tool call id");
      const args = record(event.args);
      this.toolIds.add(id);
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
      if (!this.toolIds.has(id) || this.resultIds.has(id)) {
        throw new Error("uncorrelated Pi tool result");
      }
      this.resultIds.add(id);
      const result = record(event.result);
      const content = textContent(result.content ?? event.result);
      return [
        {
          type: "tool_result",
          id,
          status: event.isError ? "error" : "success",
          took_ms: 0,
          content: [{ type: "text", text: content, truncated: false }],
          metadata: { output_truncated: false },
        },
      ];
    }
    if (type === "message_end") {
      const message = record(event.message);
      if (message.role !== "assistant") return [];
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
