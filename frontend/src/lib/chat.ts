/**
 * Streaming client for the AI research assistant (`/chat`).
 *
 * The chat UI consumes a flat stream of `ChatEvent`s describing one assistant
 * turn: reasoning tokens, `search_papers` tool calls with their results, and
 * final answer tokens. This is the exact event vocabulary the FastAPI SSE
 * endpoint (`POST /api/v1/chat/stream`, `text/event-stream`) will emit — each
 * SSE message carries one JSON-encoded `ChatEvent` in its `data:` field.
 *
 * Until that endpoint ships, `streamChat` replays a scripted mock stream
 * (see `chatMock.ts`). Set `VITE_CHAT_LIVE=1` at build time to switch to the
 * real endpoint without touching any UI code.
 *
 * Answer text protocol: answer deltas concatenate into GitHub-flavored Markdown,
 * with inline paper citations of the form `[label](paper:<route_id>)`.
 * Citations are resolved client-side against the papers returned by earlier
 * `tool_result` events (see `ChatMarkdown.tsx`).
 *
 * The wire contract below (hit shape, event vocabulary) is the one agreed in
 * PLAN_CHAT_ENDPOINT.md (decisions 8–12): hits carry bounded `content` plus a
 * structured `metadata` dict, are keyed by `route_id` (arXiv ID for arXiv
 * papers, internal numeric ID for external resources), and deliberately carry
 * no relevance score until a calibrated reranker exists.
 */

import { apiUrl } from "@/lib/apiUrl";
import { mockChatStream } from "@/lib/chatMock";

/** Structured metadata for one search hit (PLAN_CHAT_ENDPOINT.md, decision 12).
 * Keys are always present; unavailable values are null / empty lists. */
export interface ChatPaperMetadata {
  arxiv_id: string | null;
  source: "arxiv" | "external";
  source_url: string | null;
  /** Backend-hosted or paper-supplied preview image. */
  thumbnail_url: string | null;
  authors: { name: string }[];
  /** ISO date, e.g. "2025-02-18". */
  published: string | null;
  /** Display name, e.g. "CVPR 2024". */
  conference: string | null;
  citation_count: number | null;
  tasks: { name: string; slug: string }[];
  methods: { name: string; slug: string }[];
  repositories: { url: string; stars: number | null }[];
  project_pages: { url: string }[];
}

/** One paper returned by the assistant's `search_papers` tool. */
export interface ChatPaperHit {
  /** Citation/route key: arXiv ID or internal numeric ID (`/paper/<route_id>`). */
  route_id: string;
  title: string;
  /** Bounded abstract or external-resource description (≤4,000 chars). */
  content: string;
  content_truncated: boolean;
  metadata: ChatPaperMetadata;
}

export type ChatEvent =
  | { type: "stream_start"; request_id: string; session_id: string | null }
  | { type: "reasoning_start" }
  | { type: "reasoning_delta"; text: string }
  | { type: "reasoning_end" }
  | { type: "tool_call"; id: string; name: string; args: Record<string, unknown> }
  | {
      type: "tool_result";
      id: string;
      hits: number;
      took_ms: number;
      results: ChatPaperHit[];
    }
  | { type: "answer_delta"; text: string }
  | { type: "done"; followups?: string[]; finish_reason?: string }
  | { type: "error"; message: string; code?: string }
  | { type: "session_title_start" }
  | { type: "session_title_delta"; text: string }
  | { type: "session_title_done"; title: string };

export interface ChatStreamRequest {
  message: string;
  session_id: string | null;
  client_message_id: string;
  initial_model?: string;
  replace_message_id?: string;
  prior_revision?: number;
}

/* ---------- UI message model (also persisted for session history) ---------- */

export interface ReasoningBlock {
  kind: "reasoning";
  text: string;
  /** True while reasoning tokens are still streaming in. */
  active: boolean;
  open: boolean;
}

export interface ToolBlock {
  kind: "tool";
  id: string;
  name: string;
  args: Record<string, unknown>;
  status: "running" | "done";
  hits?: number;
  took_ms?: number;
  results?: ChatPaperHit[];
  open: boolean;
}

export interface AnswerBlock {
  kind: "answer";
  text: string;
  done: boolean;
}

export type ChatBlock = ReasoningBlock | ToolBlock | AnswerBlock;

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  /** User messages: the raw question. */
  text?: string;
  /** Assistant messages: ordered stream blocks. */
  blocks?: ChatBlock[];
  streaming?: boolean;
  followups?: string[];
  /** From the `done` event; anything other than "success" is surfaced. */
  finishReason?: string;
  error?: string;
  revision?: number;
  status?: string;
}

export const isChatLive = (): boolean => {
  const raw = import.meta.env.VITE_CHAT_LIVE;
  if (!raw) return false;
  const lowered = String(raw).trim().toLowerCase();
  return lowered === "1" || lowered === "true" || lowered === "yes";
};

export interface StreamChatOptions {
  signal?: AbortSignal;
}

/**
 * Stream one assistant turn for the given conversation history (ending with
 * the newest user message). Yields `ChatEvent`s until `done` or `error`.
 */
export function streamChat(
  request: ChatStreamRequest,
  opts: StreamChatOptions = {},
): AsyncGenerator<ChatEvent> {
  if (!isChatLive()) {
    return mockChatStream(request.message, opts.signal);
  }
  return streamChatOverSSE(request, opts.signal);
}

/**
 * Real transport: POST the history, parse the `text/event-stream` response.
 * `EventSource` can't POST a body, so we read the stream off `fetch` directly.
 */
async function* streamChatOverSSE(
  request: ChatStreamRequest,
  signal?: AbortSignal,
): AsyncGenerator<ChatEvent> {
  const res = await fetch(apiUrl("/api/v1/chat/stream"), {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    credentials: "include",
    body: JSON.stringify(request),
    signal,
  });
  if (!res.ok || !res.body) {
    const payload = await res.json().catch(() => null);
    const detail = payload?.detail;
    throw new Error(detail?.message || detail || `Chat stream failed (${res.status})`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE messages are separated by a blank line; each may span multiple
      // `data:` lines that concatenate into one JSON payload.
      let sep: number;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const raw = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const data = raw
          .split("\n")
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trimStart())
          .join("\n");
        if (!data || data === "[DONE]") continue;
        yield JSON.parse(data) as ChatEvent;
      }
    }
  } finally {
    reader.releaseLock();
  }
}
