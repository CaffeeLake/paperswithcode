import {
  type ChatBrowserLatencyUpdate,
  reportChatLatency,
} from "./chat";

export type ChatTerminalClassification = NonNullable<
  ChatBrowserLatencyUpdate["terminal_classification"]
>;

type ReportLatency = (
  requestId: string,
  update: ChatBrowserLatencyUpdate,
) => void;

export class ChatLatencyTracker {
  private requestId?: string;
  private firstVisibleAt?: number;
  private streamStartReported = false;
  private firstVisibleReported = false;
  private terminalReported = false;
  private readonly semanticReported = new Set<"reasoning" | "tool" | "answer">();

  constructor(
    private readonly submittedAt: number,
    private readonly report: ReportLatency = reportChatLatency,
  ) {}

  recordStreamStart(requestId: string, now: number): void {
    this.requestId = requestId;
    if (!this.streamStartReported) {
      this.streamStartReported = true;
      this.send({
        submission_to_stream_start_ms: Math.max(0, now - this.submittedAt),
      });
    }
    this.reportFirstVisible();
  }

  recordFirstVisible(now: number): void {
    if (this.firstVisibleAt !== undefined) return;
    this.firstVisibleAt = now;
    this.reportFirstVisible();
  }

  recordSemantic(kind: "reasoning" | "tool" | "answer", now: number): void {
    if (this.semanticReported.has(kind)) return;
    this.semanticReported.add(kind);
    const elapsed = Math.max(0, now - this.submittedAt);
    this.send(kind === "reasoning"
      ? { submission_to_first_reasoning_delta_ms: elapsed }
      : kind === "tool"
        ? { submission_to_first_tool_call_ms: elapsed }
        : { submission_to_first_answer_delta_ms: elapsed });
  }

  recordTerminal(classification: ChatTerminalClassification): void {
    if (this.terminalReported) return;
    this.terminalReported = true;
    this.send({ terminal_classification: classification });
  }

  private reportFirstVisible(): void {
    if (
      !this.requestId
      || this.firstVisibleAt === undefined
      || this.firstVisibleReported
    ) return;
    this.firstVisibleReported = true;
    this.send({
      submission_to_first_visible_delta_ms: Math.max(
        0,
        this.firstVisibleAt - this.submittedAt,
      ),
    });
  }

  private send(update: ChatBrowserLatencyUpdate): void {
    if (this.requestId) this.report(this.requestId, update);
  }
}
