import { apiUrl } from "@/lib/apiUrl";
import type { ChatBlock, ChatCitation, ChatMessage } from "@/lib/chat";

export interface ChatSession {
  id: string;
  title: string;
  selected_model: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  is_busy: boolean;
}

export interface ChatSessionDetail extends ChatSession {
  transcript_status: string;
  messages: Array<{
    id: string;
    turn_id: string;
    sequence: number;
    role: "user" | "assistant";
    content: string;
    revision: number;
    status: string;
    display_blocks: ChatBlock[];
    citations: ChatCitation[];
    followups: string[];
    finish_reason?: string | null;
    error_code: string | null;
  }>;
}

export interface ChatShareSummary {
  share_id: string;
  public_path: string;
  created_at: string;
  updated_at: string;
}

export interface PublicChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  display_blocks: ChatBlock[];
  citations: ChatCitation[];
  display_state: "complete" | "interrupted" | "failed";
  finish_reason: string | null;
  error: string | null;
}

export interface ChatShareDetail {
  share_id: string;
  created_at: string;
  updated_at: string;
  messages: PublicChatMessage[];
}

export interface ChatModelChoice {
  id: string;
  label: string;
  provider: "huggingface" | "openrouter";
}

export const DEFAULT_CHAT_MODEL = "google/gemma-4-31B-it";
export const FALLBACK_CHAT_MODELS: ChatModelChoice[] = [
  { id: DEFAULT_CHAT_MODEL, label: "Gemma 4 31B", provider: "huggingface" },
  { id: "zai-org/GLM-5.2", label: "GLM 5.2", provider: "huggingface" },
  { id: "moonshotai/Kimi-K3", label: "Kimi K3", provider: "huggingface" },
  {
    id: "deepseek-ai/DeepSeek-V4-Flash-0731",
    label: "DeepSeek V4 Flash 0731",
    provider: "openrouter",
  },
];

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = payload?.detail;
    throw new Error(detail?.message || detail || `Chat request failed (${response.status})`);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

export class ChatRequestError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
  }
}

async function publicRequest<T>(path: string): Promise<T> {
  const response = await fetch(apiUrl(path), {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = payload?.detail;
    throw new ChatRequestError(
      detail?.message || detail || `Shared conversation request failed (${response.status})`,
      response.status,
    );
  }
  return response.json();
}

export async function listSessions(): Promise<ChatSession[]> {
  const sessions: ChatSession[] = [];
  let cursor: string | null = null;
  do {
    const query = new URLSearchParams({ limit: "50" });
    if (cursor) query.set("cursor", cursor);
    const page = await request<{ items: ChatSession[]; next_cursor: string | null }>(
      `/api/v1/chat/sessions?${query.toString()}`,
    );
    sessions.push(...page.items);
    cursor = page.next_cursor;
  } while (cursor && sessions.length < 100);
  return sessions;
}

export function getSession(id: string): Promise<ChatSessionDetail> {
  return request(`/api/v1/chat/sessions/${id}`);
}

export function updateSession(id: string, patch: { title?: string; selected_model?: string }): Promise<ChatSession> {
  return request(`/api/v1/chat/sessions/${id}`, { method: "PATCH", body: JSON.stringify(patch) });
}

export function removeSession(id: string): Promise<void> {
  return request(`/api/v1/chat/sessions/${id}`, { method: "DELETE" });
}

export function archiveOldChats(): Promise<{ archived_count: number }> {
  return request("/api/v1/chat/sessions/archive-old", { method: "POST" });
}

export function cancelSession(id: string): Promise<void> {
  return request(`/api/v1/chat/sessions/${id}/cancel`, { method: "POST" });
}

export function createOrRefreshShare(id: string): Promise<ChatShareSummary> {
  return request(`/api/v1/chat/sessions/${id}/share`, { method: "POST" });
}

export function getSharedChat(id: string): Promise<ChatShareDetail> {
  return publicRequest(`/api/v1/chat/shares/${encodeURIComponent(id)}`);
}

export async function getChatModels(): Promise<{ items: ChatModelChoice[]; default_model: string }> {
  return request("/api/v1/chat/models");
}

function restoreBlocks(blocks: ChatBlock[], expandFailedTools: boolean): ChatBlock[] {
  const restored = blocks.map((block): ChatBlock => block.kind === "reasoning"
    ? { ...block, active: false, open: false }
    : block.kind === "tool"
      ? {
          ...block,
          status: block.status === "running" ? "error" as const : block.status,
          open: expandFailedTools
            && (block.status === "error" || block.status === "denied" || block.status === "running"),
        }
      : { ...block, done: true as const });
  return restored.filter((block, index) => {
    const previous = restored[index - 1];
    return !(
      block.kind === "reasoning"
      && previous?.kind === "reasoning"
      && block.text === previous.text
    );
  });
}

export function toUiMessages(detail: ChatSessionDetail): ChatMessage[] {
  const failureMessage = (code: string | null): string => {
    if (code === "hf_inference_billing_exhausted") {
      return "Hugging Face could not bill this request. Your included credits may be exhausted; enable or review pay-as-you-go billing in Settings.";
    }
    if (code === "hf_inference_credential_expired") return "Your Hugging Face authorization expired. Reconnect in Settings.";
    if (code === "provider_rate_limit") return "The selected model is temporarily rate-limited. Try again shortly.";
    if (code === "provider_timeout") return "The model provider timed out. Try again shortly.";
    if (["provider_error", "provider_unavailable"].includes(code ?? "")) return "The model provider failed before completing the response. You can edit and retry your question.";
    if (code === "persistence_error") return "The response could not be saved. You can edit and retry your question.";
    if (code === "transcript_mirror_error") return "The conversation could not be saved. Please try again in a new chat.";
    return "The response did not complete. You can edit and retry your question.";
  };

  return detail.messages.flatMap((message): ChatMessage[] => {
    if (message.role === "assistant") {
      return [{
        id: message.id,
        role: "assistant",
        blocks: restoreBlocks(message.display_blocks, true),
        followups: message.followups,
        citations: message.citations,
        finishReason: message.finish_reason ?? undefined,
        streaming: false,
      }];
    }
    const userMessage: ChatMessage = {
      id: message.id,
      role: "user",
      text: message.content,
      revision: message.revision,
      status: message.status,
      error: message.status === "complete" ? undefined : message.error_code || message.status,
    };
    if (!["error", "interrupted"].includes(message.status)) return [userMessage];
    const interrupted = message.status === "interrupted";
    return [userMessage, {
      id: `${message.id}-${interrupted ? "interrupted" : "error"}`,
      role: "assistant",
      blocks: restoreBlocks(message.display_blocks, true),
      streaming: false,
      finishReason: interrupted ? "stopped" : undefined,
      error: interrupted ? undefined : failureMessage(message.error_code),
      errorCode: interrupted ? undefined : message.error_code ?? undefined,
    }];
  });
}

export function publicShareToUiMessages(detail: ChatShareDetail): ChatMessage[] {
  return detail.messages.map((message): ChatMessage => message.role === "user"
    ? { id: message.id, role: "user", text: message.content }
    : {
        id: message.id,
        role: "assistant",
        blocks: restoreBlocks(message.display_blocks, false),
        citations: message.citations,
        finishReason: message.finish_reason ?? undefined,
        error: message.error ?? undefined,
        streaming: false,
      });
}

export interface ChatSessionGroup { label: string; items: ChatSession[] }

export function groupSessions(sessions: ChatSession[]): ChatSessionGroup[] {
  const now = Date.now();
  const startOfToday = new Date().setHours(0, 0, 0, 0);
  const groups: ChatSessionGroup[] = [
    { label: "Today", items: [] },
    { label: "Previous 7 Days", items: [] },
    { label: "Previous 30 Days", items: [] },
    { label: "Older", items: [] },
  ];
  for (const session of [...sessions].sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at))) {
    const timestamp = Date.parse(session.updated_at);
    const age = now - timestamp;
    if (timestamp >= startOfToday) groups[0].items.push(session);
    else if (age < 7 * 86_400_000) groups[1].items.push(session);
    else if (age < 30 * 86_400_000) groups[2].items.push(session);
    else groups[3].items.push(session);
  }
  return groups.filter((group) => group.items.length > 0);
}
