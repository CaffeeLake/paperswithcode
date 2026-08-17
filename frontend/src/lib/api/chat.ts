import type {
  ChatAvailability,
  ChatSandboxSpendStatus,
  ChatWebSearchBudgetStatus,
  OpenRouterCredentialStatus,
  OpenRouterUsageStatus,
} from "./chat.types";
export type * from "./chat.types";
import type { ChatBrowserLatencyUpdate, ReasoningEffort } from "../chat";
import type {
  ChatModelChoice,
  ChatSession,
  ChatSessionDetail,
  ChatShareDetail,
  ChatShareSummary,
} from "../chatSessions";
import type { ApiRequest } from "../apiTransport";
import { apiFetch, apiRequest } from "./request";

export interface InferenceBillingStatus {
  connected: boolean;
}

export class ChatApi {
  constructor(private readonly request: ApiRequest) {}

  listSessions(cursor: string | null): Promise<{
    items: ChatSession[];
    next_cursor: string | null;
  }> {
    const query = new URLSearchParams({ limit: "50" });
    if (cursor) query.set("cursor", cursor);
    return this.request(`/chat/sessions?${query.toString()}`);
  }

  createSession(
    selectedModel?: string,
    reasoningEffort: ReasoningEffort = "low",
  ): Promise<ChatSession> {
    return this.request("/chat/sessions", {
      method: "POST",
      body: JSON.stringify({
        selected_model: selectedModel || null,
        reasoning_effort: reasoningEffort,
      }),
    });
  }

  getSession(id: string): Promise<ChatSessionDetail> {
    return this.request(`/chat/sessions/${id}`);
  }

  updateSession(
    id: string,
    patch: { title?: string; selected_model?: string; reasoning_effort?: ReasoningEffort },
  ): Promise<ChatSession> {
    return this.request(`/chat/sessions/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    });
  }

  removeSession(id: string): Promise<void> {
    return this.request(`/chat/sessions/${id}`, { method: "DELETE" });
  }

  archiveOldChats(): Promise<{ archived_count: number }> {
    return this.request("/chat/sessions/archive-old", { method: "POST" });
  }

  archiveOldestChats(): Promise<{ archived_count: number }> {
    return this.request("/chat/sessions/archive-oldest", { method: "POST" });
  }

  cancelSession(id: string): Promise<void> {
    return this.request(`/chat/sessions/${id}/cancel`, { method: "POST" });
  }

  createOrRefreshShare(id: string): Promise<ChatShareSummary> {
    return this.request(`/chat/sessions/${id}/share`, { method: "POST" });
  }

  getSharedChat(id: string): Promise<ChatShareDetail> {
    return this.request(`/chat/shares/${encodeURIComponent(id)}`, {
      credentials: "omit",
    });
  }

  getModels(): Promise<{ items: ChatModelChoice[]; default_model: string }> {
    return this.request("/chat/models");
  }

  getUsage(): Promise<OpenRouterUsageStatus> {
    return this.request("/chat/usage", { cache: "no-store" });
  }

  getAvailability(): Promise<ChatAvailability> {
    return this.request("/chat/availability", { cache: "no-store" });
  }

  getInferenceBilling(): Promise<InferenceBillingStatus> {
    return this.request("/me/inference-billing", { cache: "no-store" });
  }

  prewarmPaperContext(routeId: string): Promise<void> {
    return this.request("/chat/paper-context/prewarm", {
      method: "POST",
      body: JSON.stringify({ route_id: routeId }),
      credentials: "omit",
      cache: "no-store",
    });
  }

  getSandboxSpend(environment?: string): Promise<ChatSandboxSpendStatus> {
    const query = environment ? `?environment=${encodeURIComponent(environment)}` : "";
    return this.request(`/chat/admin/sandbox-spend${query}`, { cache: "no-store" });
  }

  getWebSearchBudget(): Promise<ChatWebSearchBudgetStatus> {
    return this.request("/chat/admin/web-search-budget", { cache: "no-store" });
  }

  getOpenRouterCredential(): Promise<OpenRouterCredentialStatus> {
    return this.request("/chat/openrouter-key", { cache: "no-store" });
  }

  connectOpenRouterCredential(apiKey: string): Promise<OpenRouterCredentialStatus> {
    return this.request("/chat/openrouter-key", {
      method: "PUT",
      body: JSON.stringify({ api_key: apiKey }),
    });
  }

  setOpenRouterFallback(enabled: boolean): Promise<OpenRouterCredentialStatus> {
    return this.request("/chat/openrouter-key", {
      method: "PATCH",
      body: JSON.stringify({ enabled }),
    });
  }

  disconnectOpenRouterCredential(): Promise<void> {
    return this.request("/chat/openrouter-key", { method: "DELETE" });
  }

  reportLatency(requestId: string, update: ChatBrowserLatencyUpdate): Promise<Response> {
    return apiFetch(`/chat/latency/${encodeURIComponent(requestId)}`, {
      method: "POST",
      keepalive: true,
      body: JSON.stringify(update),
    });
  }

  reportFeedback(messageId: string, value: boolean): Promise<void> {
    return this.request(`/chat/messages/${encodeURIComponent(messageId)}/feedback`, {
      method: "POST",
      body: JSON.stringify({ value }),
    });
  }

  stream(body: unknown, signal?: AbortSignal): Promise<Response> {
    return apiFetch("/chat/stream", {
      method: "POST",
      headers: { Accept: "text/event-stream" },
      body: JSON.stringify(body),
      signal,
    });
  }

  resumeStream(sessionId: string, signal?: AbortSignal): Promise<Response> {
    return apiFetch(`/chat/sessions/${encodeURIComponent(sessionId)}/stream`, {
      method: "GET",
      headers: { Accept: "text/event-stream" },
      signal,
    });
  }
}

export const chatApi = new ChatApi(apiRequest);
