import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Share2, X as XIcon } from "lucide-react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import Composer from "@/components/chat/Composer";
import {
  AssistantMessage,
  UserMessage,
} from "@/components/chat/ChatMessage";
import { PanelIcon, PlusIcon, Spinner, TrashIcon } from "@/components/chat/icons";
import { hfLoginUrl } from "@/components/HfSignInButton";
import { useToast } from "@/components/ui/use-toast";
import { useChat } from "@/hooks/useChat";
import { isChatLive, type ChatDraft, type ReasoningEffort } from "@/lib/chat";
import {
  CHAT_AUTO_SEND_KEY,
  CHAT_AUTH_ATTEMPTED_KEY,
  CHAT_DRAFT_KEY,
  CHAT_MODEL_KEY,
  CHAT_REASONING_EFFORT_KEY,
  clearQueuedChatLaunch,
  readQueuedChatLaunch,
} from "@/lib/chatLaunch";
import { SUGGESTED_CHAT_PROMPTS } from "@/lib/chatPrompts";
import { apiClient } from "@/lib/api";
import { apiUrl, isStagingEnvironment } from "@/lib/apiUrl";
import { useAuth } from "@/lib/authContext";
import {
  OPENROUTER_CREDENTIAL_QUERY_KEY,
  OPENROUTER_USAGE_QUERY_KEY,
  resetTimeLabels,
  useOpenRouterCredential,
  useOpenRouterUsage,
} from "@/lib/openrouter";
import {
  DEFAULT_CHAT_MODEL,
  PRODUCTION_FALLBACK_CHAT_MODELS,
  STAGING_FALLBACK_CHAT_MODELS,
  type ChatModelChoice,
  type ChatSession,
  archiveOldChats,
  archiveOldestChats,
  createOrRefreshShare,
  getChatModels,
  getSession,
  groupSessions,
  listSessions,
  removeSession,
  toUiMessages,
  updateSession,
} from "@/lib/chatSessions";

const HF_INFERENCE_USAGE_URL = "https://huggingface.co/settings/inference-providers";
const PRODUCTION_CHAT_URL = "https://paperswithcode.co/chat";
const BILLING_NOTICE_DISMISSED_KEY = "pwc.chat.billing-notice-dismissed.v1";
const emptyDraft = (text = ""): ChatDraft => ({ text, paperMentions: [] });
const readStoredDraft = (): ChatDraft | null => {
  const raw = sessionStorage.getItem(CHAT_DRAFT_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as ChatDraft;
    if (typeof parsed.text === "string" && Array.isArray(parsed.paperMentions)) return parsed;
  } catch { /* Legacy storage contained only the text. */ }
  return emptyDraft(raw);
};

const BillingNotice: React.FC<{ provider: ChatModelChoice["provider"] }> = ({
  provider,
}) => {
  const [dismissed, setDismissed] = useState(
    () => localStorage.getItem(BILLING_NOTICE_DISMISSED_KEY) === "1",
  );

  if (!isChatLive() || dismissed || provider !== "huggingface") return null;

  return (
    <div className="chat-billing-notice" role="note">
      <span>
        Hugging Face models use the inference permission granted when you start chatting.
        Included monthly credits are used first, then extra usage requires
        purchased credits. You can choose organization billing in Settings.
      </span>
      <div className="chat-billing-notice-actions">
        <a href="/settings">Review billing</a>
        <a href={HF_INFERENCE_USAGE_URL} target="_blank" rel="noreferrer">Review usage</a>
        <button
          type="button"
          className="chat-billing-notice-dismiss"
          aria-label="Dismiss billing notice"
          title="Dismiss"
          onClick={() => {
            localStorage.setItem(BILLING_NOTICE_DISMISSED_KEY, "1");
            setDismissed(true);
          }}
        >
          <XIcon size={15} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
};

export const OpenRouterUsageNotice: React.FC<{
  enabled: boolean;
  fallbackEnabled: boolean;
  byokExpected?: boolean;
}> = ({ enabled, fallbackEnabled, byokExpected }) => {
  const usageQuery = useOpenRouterUsage(enabled);
  if (!enabled || !usageQuery.data) return null;
  const usage = usageQuery.data;
  const reset = resetTimeLabels(usage.resets_at);
  const stagingFundingDisabled = usage.unavailable_reason === "staging_funding_disabled";
  const sharedUnavailable = usage.unavailable_reason === "shared_credits_exhausted"
    || usage.unavailable_reason === "workspace_limit_exhausted"
    || usage.unavailable_reason === "provider_status_unavailable";
  return <div className="chat-openrouter-usage" role="status">
    <span>
      {stagingFundingDisabled
        ? <strong>Chat is now live on paperswithcode.co</strong>
        : sharedUnavailable
        ? <><strong>Shared OpenRouter credits unavailable</strong> · {usage.remaining_percent}% of your allowance remains</>
        : <><strong>{usage.remaining_percent}% left</strong> this month · resets {reset.local}</>}
    </span>
    {stagingFundingDisabled ? <span>
      <a href={usage.production_chat_url || PRODUCTION_CHAT_URL}>Continue on production</a>
      {fallbackEnabled && " · Your connected OpenRouter key remains available on staging."}
    </span> : (!usage.available || byokExpected) && <span>
      {fallbackEnabled
        ? "Your connected OpenRouter key will be used on your next explicit send."
        : <><a href="/settings#openrouter-byok">Connect your own key in Settings</a> to continue.</>}
    </span>}
  </div>;
};

export const ChatCapacityDialog: React.FC<{
  retryAt: number;
  onRetry: () => void;
  onCancel: () => void;
}> = ({ retryAt, onRetry, onCancel }) => {
  const [remaining, setRemaining] = useState(() => Math.max(0, Math.ceil((retryAt - Date.now()) / 1_000)));
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const previouslyFocused = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    cancelRef.current?.focus();
    const update = () => setRemaining(Math.max(0, Math.ceil((retryAt - Date.now()) / 1_000)));
    update();
    const timer = window.setInterval(update, 250);
    return () => {
      window.clearInterval(timer);
      previouslyFocused?.focus();
    };
  }, [retryAt]);

  return (
    <div className="chat-capacity-dialog-backdrop" role="presentation">
      <div
        className="chat-capacity-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="chat-capacity-dialog-title"
        aria-describedby="chat-capacity-dialog-description"
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            onCancel();
          }
        }}
      >
        <h2 id="chat-capacity-dialog-title">All research slots are currently in use</h2>
        <p id="chat-capacity-dialog-description">
          Your message was not sent or billed. Try again in a few seconds.
        </p>
        <p className="chat-capacity-countdown" aria-live="polite">
          {remaining > 0 ? `Try again available in ${remaining} second${remaining === 1 ? "" : "s"}.` : "You can try again now."}
        </p>
        <div className="chat-capacity-dialog-actions">
          <button type="button" className="chat-capacity-cancel" ref={cancelRef} onClick={onCancel}>Cancel</button>
          <button type="button" className="chat-capacity-retry" disabled={remaining > 0} onClick={onRetry}>Try again</button>
        </div>
      </div>
    </div>
  );
};

export const ChatDisabledDialog: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeRef.current?.focus();
    return () => previouslyFocused?.focus();
  }, []);
  return <div className="chat-capacity-dialog-backdrop" role="presentation">
    <div className="chat-capacity-dialog" role="dialog" aria-modal="true"
      aria-labelledby="chat-disabled-title" aria-describedby="chat-disabled-description"
      onKeyDown={(event) => { if (event.key === "Escape") { event.preventDefault(); onClose(); } }}>
      <h2 id="chat-disabled-title">Chat is temporarily disabled</h2>
      <p id="chat-disabled-description">We've temporarily paused new research runs. Your message wasn't sent, and your draft is still here. Please try again later.</p>
      <div className="chat-capacity-dialog-actions">
        <button ref={closeRef} type="button" className="chat-capacity-cancel" onClick={onClose}>Keep editing</button>
      </div>
    </div>
  </div>;
};

type RouteSessionState = {
  id: string;
  status: "loading" | "loaded" | "error";
  error?: string;
};

const ChatView: React.FC = () => {
  const { sessionId: routeSessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user, isLoading: authLoading } = useAuth();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const staging = isStagingEnvironment();
  const availabilityQuery = useQuery({
    queryKey: ["chatAvailability"],
    queryFn: () => apiClient.getChatAvailability(),
    refetchInterval: 30000,
    retry: false,
    enabled: isChatLive() && Boolean(user),
  });
  const chatPaused = availabilityQuery.data?.status === "paused";
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [sessionError, setSessionError] = useState("");
  const [routeSessionState, setRouteSessionState] = useState<RouteSessionState | null>(
    () => routeSessionId ? { id: routeSessionId, status: "loading" } : null,
  );
  const [routeLoadAttempt, setRouteLoadAttempt] = useState(0);
  const queuedLaunchRef = useRef(readQueuedChatLaunch());
  const requestedModelRef = useRef(searchParams.get("model") || queuedLaunchRef.current?.model);
  const [models, setModels] = useState<ChatModelChoice[]>(
    staging ? STAGING_FALLBACK_CHAT_MODELS : PRODUCTION_FALLBACK_CHAT_MODELS,
  );
  const [selectedModel, setSelectedModel] = useState(
    requestedModelRef.current || DEFAULT_CHAT_MODEL,
  );
  const selectedProvider = models.find((model) => model.id === selectedModel)?.provider
    ?? "huggingface";
  const openRouterCredentialQuery = useOpenRouterCredential(
    Boolean(user && selectedProvider === "openrouter"),
  );
  const selectedProviderRef = useRef(selectedProvider);
  selectedProviderRef.current = selectedProvider;
  const [liveTitle, setLiveTitle] = useState("");
  const [draft, setDraft] = useState<ChatDraft>(() => emptyDraft());
  const [webSearchEnabled, setWebSearchEnabled] = useState(
    () => queuedLaunchRef.current?.webSearchEnabled ?? false,
  );
  const [reasoningEffort, setReasoningEffort] = useState<ReasoningEffort>(
    () => queuedLaunchRef.current?.reasoningEffort ?? "low",
  );
  const webSearchAvailable = Boolean(availabilityQuery.data?.web_search_available);
  const [pendingAutoDraft, setPendingAutoDraft] = useState<ChatDraft>(() => {
    const queryPrompt = searchParams.get("q")?.trim();
    if (queryPrompt) return emptyDraft(queryPrompt);
    return queuedLaunchRef.current?.draft ?? emptyDraft();
  });
  const autoSendStartedRef = useRef(false);
  const inferenceConnectedRef = useRef(false);
  const inferenceCheckPendingRef = useRef(false);
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");
  const [sessionMenu, setSessionMenu] = useState<{ id: string; x: number; y: number } | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(() => typeof window === "undefined" || window.innerWidth > 900);
  const [sharePending, setSharePending] = useState(false);
  const [archivePending, setArchivePending] = useState<"old" | "oldest" | null>(null);
  const [manualShareUrl, setManualShareUrl] = useState("");
  const manualTitleLockRef = useRef<Set<string>>(new Set());
  const sessionsLoadedRef = useRef(false);
  const routeSessionIdRef = useRef(routeSessionId);
  const activeStreamSessionIdRef = useRef<string | null>(null);
  const activeStreamRouteSessionIdRef = useRef<string | null>(null);
  const loadedRouteSessionIdRef = useRef<string | null>(null);
  routeSessionIdRef.current = routeSessionId;

  const refreshSessions = useCallback(async () => {
    if (!user) return;
    const showLoading = !sessionsLoadedRef.current;
    if (showLoading) setSessionsLoading(true);
    try {
      const fetched = await listSessions();
      setSessions((previous) => {
        const activeId = activeStreamSessionIdRef.current;
        const active = activeId ? previous.find((session) => session.id === activeId) : undefined;
        if (!active) return fetched;
        const saved = fetched.find((session) => session.id === activeId);
        const inProgress = saved ? { ...saved, title: active.title, is_busy: true } : active;
        return [inProgress, ...fetched.filter((session) => session.id !== activeId)];
      });
      sessionsLoadedRef.current = true;
      setSessionError("");
    } catch (error) {
      setSessionError(error instanceof Error ? error.message : "Could not load chats");
    } finally {
      if (showLoading) setSessionsLoading(false);
    }
  }, [user]);

  const chat = useChat({
    sessionId: routeSessionId ?? null,
    initialModel: selectedModel,
    webSearchEnabled: webSearchAvailable && webSearchEnabled,
    reasoningEffort,
    onSessionId: (id) => {
      activeStreamSessionIdRef.current = id;
      const isNewSession = id !== routeSessionIdRef.current;
      const shouldFollowStream = (
        routeSessionIdRef.current ?? null
      ) === activeStreamRouteSessionIdRef.current;
      const now = new Date().toISOString();
      setSessions((previous) => previous.some((session) => session.id === id)
        ? previous.map((session) => session.id === id ? { ...session, is_busy: true } : session)
        : [{
            id,
            title: "New chat",
            selected_model: selectedModel,
            created_at: now,
            updated_at: now,
            message_count: 1,
            is_busy: true,
            web_search_enabled: webSearchEnabled,
            reasoning_effort: reasoningEffort,
          }, ...previous]);
      if (isNewSession && shouldFollowStream) {
        setLiveTitle("New chat");
      }
      if (shouldFollowStream) {
        // Keep the in-progress response visible while the route catches up with
        // the newly persisted session announced by the SSE stream.
        loadedRouteSessionIdRef.current = id;
        setRouteSessionState({ id, status: "loaded" });
        if (isNewSession) navigate(`/chat/${id}`, { replace: true });
      }
    },
    onTitle: (title) => {
      const sessionId = activeStreamSessionIdRef.current ?? routeSessionIdRef.current;
      if (sessionId && !manualTitleLockRef.current.has(sessionId)) {
        if (sessionId === routeSessionIdRef.current) setLiveTitle(title);
        setSessions((previous) => previous.map((session) => session.id === sessionId ? { ...session, title } : session));
      }
    },
    onSettled: (sessionId) => {
      if (sessionId) {
        setSessions((previous) => previous.map((session) => session.id === sessionId
          ? { ...session, is_busy: false }
          : session));
      }
      activeStreamSessionIdRef.current = null;
      activeStreamRouteSessionIdRef.current = null;
      void refreshSessions();
    },
    onProviderTerminal: () => {
      if (selectedProviderRef.current === "openrouter") {
        void queryClient.invalidateQueries({ queryKey: OPENROUTER_USAGE_QUERY_KEY });
        void queryClient.invalidateQueries({ queryKey: OPENROUTER_CREDENTIAL_QUERY_KEY });
      }
    },
    onInterrupted: (interruptedDraft) => {
      setDraft(interruptedDraft);
    },
  });
  const loadChat = chat.load;
  const sendChat = chat.send;

  useEffect(() => {
    if (chat.capacityRequest) setDraft(chat.capacityRequest.draft);
  }, [chat.capacityRequest]);

  useEffect(() => {
    if (chat.busy) setEditingMessageId(null);
  }, [chat.busy]);

  const authorizeInference = useCallback((nextDraft: ChatDraft) => {
    sessionStorage.setItem(CHAT_DRAFT_KEY, JSON.stringify(nextDraft));
    sessionStorage.setItem(CHAT_MODEL_KEY, selectedModel);
    sessionStorage.setItem(CHAT_REASONING_EFFORT_KEY, reasoningEffort);
    sessionStorage.setItem(CHAT_AUTO_SEND_KEY, "1");
    sessionStorage.setItem(CHAT_AUTH_ATTEMPTED_KEY, "1");
    const returnTo = routeSessionIdRef.current
      ? `/chat/${routeSessionIdRef.current}`
      : "/chat";
    window.location.href = hfLoginUrl(returnTo, selectedProvider === "huggingface");
  }, [reasoningEffort, selectedModel, selectedProvider]);

  const restoreAuthorizationPrompt = useCallback((nextDraft: ChatDraft, message: string) => {
    sessionStorage.setItem(CHAT_DRAFT_KEY, JSON.stringify(nextDraft));
    sessionStorage.setItem(CHAT_MODEL_KEY, selectedModel);
    sessionStorage.removeItem(CHAT_AUTO_SEND_KEY);
    sessionStorage.removeItem(CHAT_AUTH_ATTEMPTED_KEY);
    setPendingAutoDraft(emptyDraft());
    setDraft(nextDraft);
    setSessionError(message);
  }, [selectedModel]);

  const send = useCallback(async (nextDraft: ChatDraft) => {
    if (!user) {
      authorizeInference(nextDraft);
      return;
    }
    if (selectedProvider === "huggingface" && !inferenceConnectedRef.current) {
      if (inferenceCheckPendingRef.current) return;
      inferenceCheckPendingRef.current = true;
      try {
        const response = await fetch(apiUrl("/api/v1/me/inference-billing"), {
          credentials: "include",
          cache: "no-store",
        });
        if (!response.ok) throw new Error("Could not check Hugging Face authorization.");
        const billing = (await response.json()) as { connected: boolean };
        if (!billing.connected) {
          if (sessionStorage.getItem(CHAT_AUTH_ATTEMPTED_KEY) === "1") {
            restoreAuthorizationPrompt(
              nextDraft,
              "Hugging Face inference authorization was not completed. Your prompt is ready to retry.",
            );
            return;
          }
          authorizeInference(nextDraft);
          return;
        }
        inferenceConnectedRef.current = true;
      } catch (error) {
        restoreAuthorizationPrompt(
          nextDraft,
          error instanceof Error
            ? error.message
            : "Could not check Hugging Face authorization.",
        );
        return;
      } finally {
        inferenceCheckPendingRef.current = false;
      }
    }
    const streamRouteSessionId = routeSessionIdRef.current ?? null;
    sessionStorage.removeItem(CHAT_AUTO_SEND_KEY);
    if (!sendChat(nextDraft)) {
      restoreAuthorizationPrompt(
        nextDraft,
        "Your prompt was not sent. It is ready to retry.",
      );
      return;
    }
    activeStreamRouteSessionIdRef.current = streamRouteSessionId;
    activeStreamSessionIdRef.current = streamRouteSessionId;
    sessionStorage.removeItem(CHAT_DRAFT_KEY);
    sessionStorage.removeItem(CHAT_MODEL_KEY);
    sessionStorage.removeItem(CHAT_AUTH_ATTEMPTED_KEY);
    clearQueuedChatLaunch();
    setDraft(emptyDraft());
  }, [authorizeInference, restoreAuthorizationPrompt, selectedProvider, sendChat, user]);

  useEffect(() => {
    if (authLoading || !user) return;
    const savedModel = sessionStorage.getItem(CHAT_MODEL_KEY);
    if (savedModel) setSelectedModel(savedModel);
    void refreshSessions();
    void getChatModels().then((result) => {
      setModels(result.items);
      if (!routeSessionIdRef.current) {
        const requestedModel = requestedModelRef.current || savedModel;
        setSelectedModel(
          requestedModel && result.items.some((model) => model.id === requestedModel)
            ? requestedModel
            : result.default_model,
        );
      }
    });
    const savedDraft = readStoredDraft();
    const shouldAutoSend = sessionStorage.getItem(CHAT_AUTO_SEND_KEY) === "1";
    if (savedDraft) {
      if (shouldAutoSend) setPendingAutoDraft(savedDraft);
      else setDraft(savedDraft);
    }
  }, [authLoading, refreshSessions, user]);

  useEffect(() => {
    if (!routeSessionId) {
      // Do not reset an already-new chat when its request flips `busy` to
      // true. This effect also watches `chat.busy` so saved routes can load
      // after an in-flight turn settles; resetting unconditionally here
      // aborted brand-new turns before their first SSE event arrived.
      if (loadedRouteSessionIdRef.current !== null) {
        loadedRouteSessionIdRef.current = null;
        chat.reset();
        setWebSearchEnabled(false);
        setReasoningEffort("low");
      }
      setRouteSessionState(null);
      return;
    }
    if (loadedRouteSessionIdRef.current === routeSessionId) return;
    setRouteSessionState((previous) => previous?.id === routeSessionId && previous.status === "loading"
      ? previous
      : { id: routeSessionId, status: "loading" });
    if (authLoading || !user) return;

    let cancelled = false;
    setSessionError("");
    void getSession(routeSessionId).then((detail) => {
      if (cancelled) return;
      chat.load(toUiMessages(detail), routeSessionId, detail.is_busy);
      setSelectedModel(detail.selected_model);
      setWebSearchEnabled(
        queuedLaunchRef.current && detail.messages.length === 0
          ? queuedLaunchRef.current.webSearchEnabled
          : detail.web_search_enabled,
      );
      setReasoningEffort(
        queuedLaunchRef.current && detail.messages.length === 0
          ? queuedLaunchRef.current.reasoningEffort
          : detail.reasoning_effort ?? "high",
      );
      setLiveTitle(detail.title);
      loadedRouteSessionIdRef.current = routeSessionId;
      setRouteSessionState({ id: routeSessionId, status: "loaded" });
    }).catch((error) => {
      if (cancelled) return;
      const message = error instanceof Error ? error.message : "Chat not found";
      chat.reset();
      setSessionError(message);
      setRouteSessionState({ id: routeSessionId, status: "error", error: message });
    });
    return () => { cancelled = true; };
    // Loading is intentionally keyed to the route. `chat.load` detaches the
    // visible transcript without cancelling an active stream.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, routeSessionId, user, chat.busy, routeLoadAttempt]);

  useEffect(() => {
    const prompt = searchParams.get("q")?.trim();
    if (!prompt) return;
    autoSendStartedRef.current = false;
    const requestedModel = searchParams.get("model");
    if (requestedModel) setSelectedModel(requestedModel);
    setPendingAutoDraft(emptyDraft(prompt));
    const next = new URLSearchParams(searchParams);
    next.delete("q");
    next.delete("model");
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    if (
      authLoading
      || chat.busy
      || !pendingAutoDraft.text
      || autoSendStartedRef.current
      || (Boolean(user) && webSearchEnabled && availabilityQuery.isFetching)
      || (routeSessionId && routeSessionState?.status !== "loaded")
    ) return;
    // Deferring avoids React StrictMode's development-only effect cleanup from
    // aborting the request before the second effect pass can own it.
    const timer = window.setTimeout(() => {
      if (autoSendStartedRef.current) return;
      autoSendStartedRef.current = true;
      const nextDraft = pendingAutoDraft;
      void send(nextDraft).finally(() => setPendingAutoDraft(emptyDraft()));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [
    authLoading,
    availabilityQuery.isFetching,
    chat.busy,
    pendingAutoDraft,
    routeSessionId,
    routeSessionState?.status,
    send,
    user,
    webSearchEnabled,
  ]);

  useEffect(() => {
    const onFocus = () => {
      if (!user || chat.busy) return;
      void refreshSessions();
    };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [chat.busy, refreshSessions, user]);

  useEffect(() => {
    if (!sessionMenu) return;
    const close = () => setSessionMenu(null);
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") close(); };
    window.addEventListener("click", close);
    window.addEventListener("keydown", onKey);
    return () => { window.removeEventListener("click", close); window.removeEventListener("keydown", onKey); };
  }, [sessionMenu]);

  const newChat = () => {
    activeStreamSessionIdRef.current = null;
    chat.reset();
    setDraft(emptyDraft());
    setWebSearchEnabled(false);
    setReasoningEffort("low");
    setLiveTitle("");
    navigate("/chat");
  };
  const saveRename = async (id: string) => {
    const title = editingTitle.trim();
    if (!title) return;
    try {
      const updated = await updateSession(id, { title });
      manualTitleLockRef.current.add(id);
      if (id === routeSessionId) setLiveTitle(updated.title);
      setSessions((previous) => previous.map((session) => session.id === id ? updated : session));
      setEditingId(null);
    } catch (error) { setSessionError(error instanceof Error ? error.message : "Rename failed"); }
  };
  const remove = async (id: string) => {
    const active = id === routeSessionId && chat.busy;
    if (!window.confirm(active ? "Stop and delete this chat? This cannot be undone." : "Delete this chat? This cannot be undone.")) return;
    if (active) chat.stop();
    try {
      if (active) {
        const deadline = Date.now() + 3_000;
        for (;;) {
          const detail = await getSession(id);
          if (!detail.is_busy) break;
          if (Date.now() >= deadline) throw new Error("Generation is still stopping. The chat was not deleted.");
          await new Promise((resolve) => window.setTimeout(resolve, 150));
        }
      }
      await removeSession(id); if (id === routeSessionId) newChat(); await refreshSessions();
    }
    catch (error) { setSessionError(error instanceof Error ? error.message : "Delete failed"); }
  };
  const archiveOld = async () => {
    if (archivePending !== null) return;
    setArchivePending("old");
    try {
      const result = await archiveOldChats();
      await refreshSessions();
      if (result.archived_count === 0) {
        toast({
          title: "No chats were archived",
          description: "There are no inactive chats older than 30 days.",
        });
        return;
      }
      const failedMessage = [...chat.messages].reverse().find((message) => message.role === "user");
      chat.reset();
      setDraft({ text: failedMessage?.text ?? "", paperMentions: failedMessage?.paperMentions ?? [] });
      setLiveTitle("");
      toast({
        title: `${result.archived_count} ${result.archived_count === 1 ? "chat" : "chats"} archived`,
        description: "Your question is ready to send again.",
      });
    } catch (error) {
      toast({
        variant: "destructive",
        title: "Could not archive old chats",
        description: error instanceof Error ? error.message : "Try again.",
      });
    } finally {
      setArchivePending(null);
    }
  };
  const archiveOldest = async () => {
    if (archivePending !== null) return;
    setArchivePending("oldest");
    try {
      const result = await archiveOldestChats();
      await refreshSessions();
      const failedMessage = [...chat.messages].reverse().find((message) => message.role === "user");
      chat.reset();
      setDraft({ text: failedMessage?.text ?? "", paperMentions: failedMessage?.paperMentions ?? [] });
      setLiveTitle("");
      toast({
        title: `${result.archived_count} ${result.archived_count === 1 ? "chat" : "chats"} archived`,
        description: "Your question is ready to send again.",
      });
    } catch (error) {
      toast({
        variant: "destructive",
        title: "Could not archive chats",
        description: error instanceof Error ? error.message : "Try again.",
      });
    } finally {
      setArchivePending(null);
    }
  };
  const changeModel = async (model: string) => {
    const previousModel = selectedModel;
    setSelectedModel(model);
    if (!routeSessionId) return;
    try {
      const updated = await updateSession(routeSessionId, { selected_model: model });
      setSessions((previous) => previous.map((session) => session.id === routeSessionId
        ? { ...session, selected_model: updated.selected_model }
        : session));
      setSessionError("");
    }
    catch (error) { setSelectedModel(previousModel); setSessionError(error instanceof Error ? error.message : "Model change failed"); }
  };

  const changeReasoningEffort = async (effort: ReasoningEffort) => {
    const previousEffort = reasoningEffort;
    setReasoningEffort(effort);
    if (!routeSessionId) return;
    try {
      const updated = await updateSession(routeSessionId, {
        reasoning_effort: effort,
      });
      setSessions((previous) => previous.map((session) => (
        session.id === routeSessionId ? updated : session
      )));
    } catch (error) {
      setReasoningEffort(previousEffort);
      setSessionError(
        error instanceof Error ? error.message : "Effort change failed",
      );
    }
  };
  const shareChat = async () => {
    if (!routeSessionId || chat.busy || sharePending) return;
    setSharePending(true);
    try {
      const share = await createOrRefreshShare(routeSessionId);
      const url = new URL(share.public_path, window.location.origin).toString();
      try {
        if (!navigator.clipboard?.writeText) throw new Error("Clipboard unavailable");
        await navigator.clipboard.writeText(url);
        toast({
          className: "chat-share-toast",
          duration: 5_000,
          title: "Public link copied to your clipboard",
          description: "Anyone with this link can see this conversation.",
        });
      } catch {
        setManualShareUrl(url);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Could not share this conversation";
      setSessionError(message);
      toast({ variant: "destructive", title: "Share failed", description: message });
    } finally {
      setSharePending(false);
    }
  };

  const [headerHeight, setHeaderHeight] = useState(60);
  useLayoutEffect(() => {
    const element = document.querySelector<HTMLElement>(".app-header");
    if (!element) return;
    const update = () => setHeaderHeight(element.offsetHeight);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const scrollRef = useRef<HTMLDivElement>(null);
  const scrollTopBeforeToggleRef = useRef<number | null>(null);
  const editScrollAnchorRef = useRef<string | null>(null);
  useEffect(() => {
    if (!chat.busy) editScrollAnchorRef.current = null;
  }, [chat.busy]);
  const toggleBlock = (messageId: string, blockIndex: number) => {
    scrollTopBeforeToggleRef.current = scrollRef.current?.scrollTop ?? null;
    chat.toggleBlock(messageId, blockIndex);
  };
  useLayoutEffect(() => {
    const scrollElement = scrollRef.current;
    if (!scrollElement) return;
    if (scrollTopBeforeToggleRef.current !== null) {
      scrollElement.scrollTop = scrollTopBeforeToggleRef.current;
      scrollTopBeforeToggleRef.current = null;
      return;
    }
    if (editScrollAnchorRef.current) {
      const target = Array.from(
        scrollElement.querySelectorAll<HTMLElement>("[data-message-id]"),
      ).find((element) => element.dataset.messageId === editScrollAnchorRef.current);
      if (target) {
        const containerRect = scrollElement.getBoundingClientRect();
        const targetRect = target.getBoundingClientRect();
        scrollElement.scrollTop += targetRect.top - containerRect.top - 24;
        return;
      }
    }
    scrollElement.scrollTop = scrollElement.scrollHeight;
  }, [chat.messages]);

  const current = sessions.find((session) => session.id === routeSessionId);
  const userMessages = chat.messages.filter((message) => message.role === "user");
  const firstUserId = userMessages[0]?.id;
  const latestUserId = userMessages.at(-1)?.id;
  const isEmpty = chat.messages.length === 0;
  const lastOpenRouterError = [...chat.messages].reverse().find(
    (message) => message.role === "assistant" && message.errorCode,
  )?.errorCode;
  const byokExpected = lastOpenRouterError === "openrouter_unavailable"
    || lastOpenRouterError === "openrouter_monthly_budget_exhausted";
  const routeStateMatches = routeSessionState?.id === routeSessionId;
  const isRouteSessionLoading = Boolean(routeSessionId && (
    authLoading || (user && (!routeStateMatches || routeSessionState?.status === "loading"))
  ));
  const routeSessionError = routeStateMatches && routeSessionState?.status === "error"
    ? routeSessionState.error
    : undefined;

  return (
    <div className="chat-page" style={{ height: `calc(100dvh - ${headerHeight}px)` }}>
      <aside className={`chat-sidebar${sidebarOpen ? "" : " chat-sidebar-closed"}`}>
        <div className="chat-sidebar-top">
          <button type="button" className="chat-new-chat" onClick={newChat}><PlusIcon /> New chat</button>
          <button type="button" className="icon-btn" onClick={() => setSidebarOpen(false)} title="Collapse sidebar"><PanelIcon /></button>
        </div>
        <nav className="chat-sessions" aria-label="Chat history">
          {sessionsLoading && <div className="chat-sessions-empty">Loading chats…</div>}
          {!sessionsLoading && sessionError && <div className="chat-sessions-empty">{sessionError}</div>}
          {!sessionsLoading && !sessionError && sessions.length === 0 && <div className="chat-sessions-empty">Conversations you start will show up here.</div>}
          {groupSessions(sessions).map((group) => <div className="chat-session-group" key={group.label}>
            <div className="chat-session-group-label">{group.label}</div>
            {group.items.map((session) => <div
              key={session.id}
              className={`chat-session${session.id === routeSessionId ? " chat-session-active" : ""}`}
              role="button" tabIndex={0}
              onClick={() => navigate(`/chat/${session.id}`)}
              onKeyDown={(event) => {
                if (event.key === "Enter") navigate(`/chat/${session.id}`);
                if (event.key === "F2") { setEditingId(session.id); setEditingTitle(session.title); }
                if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) {
                  event.preventDefault();
                  const rect = event.currentTarget.getBoundingClientRect();
                  setSessionMenu({ id: session.id, x: rect.right - 150, y: rect.bottom });
                }
              }}
              onContextMenu={(event) => { event.preventDefault(); setSessionMenu({ id: session.id, x: event.clientX, y: event.clientY }); }}
            >
              {editingId === session.id ? <input
                className="chat-session-title-input" value={editingTitle} autoFocus maxLength={80}
                onClick={(event) => event.stopPropagation()}
                onChange={(event) => setEditingTitle(event.target.value)}
                onBlur={() => void saveRename(session.id)}
                onKeyDown={(event) => { event.stopPropagation(); if (event.key === "Enter") void saveRename(session.id); if (event.key === "Escape") setEditingId(null); }}
              /> : <span className="chat-session-title">{session.title}</span>}
              <button type="button" className="chat-session-menu" aria-label="Chat actions" aria-haspopup="menu" title="Chat actions" onClick={(event) => { event.stopPropagation(); const rect = event.currentTarget.getBoundingClientRect(); setSessionMenu({ id: session.id, x: rect.right - 150, y: rect.bottom }); }}>⋯</button>
              <button type="button" className="chat-session-delete" aria-label="Delete conversation" onClick={(event) => { event.stopPropagation(); void remove(session.id); }}><TrashIcon /></button>
            </div>)}
          </div>)}
        </nav>
        {sessionMenu && <div className="chat-session-context-menu" role="menu" style={{ left: sessionMenu.x, top: sessionMenu.y }} onClick={(event) => event.stopPropagation()}>
          <button type="button" role="menuitem" autoFocus onClick={() => {
            const session = sessions.find((item) => item.id === sessionMenu.id);
            if (session) { setEditingId(session.id); setEditingTitle(session.title); }
            setSessionMenu(null);
          }}>Rename chat</button>
        </div>}
      </aside>

      <section className="chat-main">
        <div className="chat-topbar">
          {!sidebarOpen && <button type="button" className="icon-btn" onClick={() => setSidebarOpen(true)} title="Open sidebar"><PanelIcon /></button>}
          <span className="chat-topbar-title">{isRouteSessionLoading
            ? current?.title || ""
            : liveTitle || current?.title || (isEmpty ? "" : "New chat")}</span>
          {staging && <span className="chat-staging-badge">Staging</span>}
          {routeSessionId && routeStateMatches && routeSessionState?.status === "loaded" && !isEmpty && (
            <button
              type="button"
              className="chat-share-button"
              onClick={() => void shareChat()}
              disabled={chat.busy || sharePending || isRouteSessionLoading}
              aria-label="Share conversation"
            >
              {sharePending ? <Spinner /> : <Share2 aria-hidden="true" />}
              <span>Share</span>
            </button>
          )}
        </div>

        {isRouteSessionLoading && !pendingAutoDraft.text ? <div className="chat-session-loading" role="status" aria-live="polite">
          <Spinner />
          <span>Loading conversation…</span>
        </div> : routeSessionError ? <div className="chat-session-load-error" role="alert">
          <p>{routeSessionError}</p>
          <button type="button" onClick={() => {
            setRouteSessionState({ id: routeSessionId!, status: "loading" });
            setRouteLoadAttempt((attempt) => attempt + 1);
          }}>Try again</button>
        </div> : isEmpty && !pendingAutoDraft.text ? <div className="chat-empty"><div className="chat-empty-inner">
          <div className="chat-empty-eyebrow">AI research assistant · Staging preview</div>
          <h1 className="chat-empty-title">Ask <em>Papers With Code</em></h1>
          <p className="chat-empty-sub">Answers are grounded in a live hybrid search over papers, tasks, and benchmarks — with citations you can follow.</p>
          {staging && <p className="chat-staging-access-note">
            This is a limited staging preview. Only approved Hugging Face users can start chats.
          </p>}
          <BillingNotice provider={selectedProvider} />
          <OpenRouterUsageNotice
            enabled={selectedProvider === "openrouter"}
            fallbackEnabled={Boolean(openRouterCredentialQuery.data?.fallback_enabled)}
            byokExpected={byokExpected}
          />
          {chatPaused && <div id="chat-paused-description" className="chat-paused-banner" role="status">Chat is temporarily disabled. You can keep browsing and editing your conversations. New research runs will return when chat is restored.</div>}
          <Composer onSend={send} busy={chat.busy} onStop={chat.stop} autoFocus draft={draft} onDraftChange={setDraft} models={models} selectedModel={selectedModel} onModelChange={(model) => void changeModel(model)} disabled={chatPaused} describedBy={chatPaused ? "chat-paused-description" : undefined} paperMentionsEnabled={Boolean(availabilityQuery.data?.paper_mentions_enabled)} webSearchAvailable={webSearchAvailable} webSearchEnabled={webSearchEnabled} onWebSearchChange={setWebSearchEnabled} reasoningEffort={reasoningEffort} onReasoningEffortChange={(effort) => void changeReasoningEffort(effort)} />
          <div className="chat-examples">{SUGGESTED_CHAT_PROMPTS.map((example) => <button type="button" key={example} className="chat-example" disabled={chatPaused} onClick={() => send(emptyDraft(example))}>{example}</button>)}</div>
        </div></div> : <>
          {chat.sessionError && <div className="chat-session-error" role="alert">{chat.sessionError}</div>}
          <div className="chat-conversation" ref={scrollRef}><div className="chat-conversation-inner">
            {isEmpty && pendingAutoDraft.text && <UserMessage
              id="queued-launch-preview"
              text={pendingAutoDraft.text}
              paperMentions={pendingAutoDraft.paperMentions}
              isInitial
            />}
            {chat.messages.map((message) => message.role === "user"
              ? <UserMessage
                  key={message.id}
                  id={message.id}
                  text={message.text ?? ""}
                  paperMentions={message.paperMentions ?? []}
                  paperMentionsEnabled={Boolean(availabilityQuery.data?.paper_mentions_enabled)}
                  isInitial={message.id === firstUserId}
                  editingAllowed={!chat.busy && Boolean(message.revision)}
                  editing={editingMessageId === message.id}
                  editNotice={message.id === firstUserId
                    ? "Sending will replace this conversation."
                    : message.id === latestUserId
                      ? "Sending will replace the response."
                      : "Sending will replace the response and all messages after it."}
                  onEdit={() => setEditingMessageId(message.id)}
                  onCancel={() => setEditingMessageId(null)}
                  onResendDraft={(nextDraft) => {
                    if (message.id !== firstUserId) editScrollAnchorRef.current = message.id;
                    const accepted = chat.editAndResend(message.id, nextDraft);
                    if (accepted) setEditingMessageId(null);
                    else editScrollAnchorRef.current = null;
                    return accepted;
                  }}
                />
              : <AssistantMessage
                  key={message.id}
                  msg={message}
                  papers={chat.papers}
                  onToggleBlock={toggleBlock}
                  onArchiveOldChats={() => void archiveOld()}
                  onArchiveOldestChats={() => void archiveOldest()}
                  archivePending={archivePending}
                  hfBilling={null}
                  openRouterFallbackEnabled={Boolean(openRouterCredentialQuery.data?.fallback_enabled)}
                />)}
          </div></div>
          <div className="chat-composer-wrap"><div className="chat-composer-inner">
            <BillingNotice provider={selectedProvider} />
            <OpenRouterUsageNotice
              enabled={selectedProvider === "openrouter"}
              fallbackEnabled={Boolean(openRouterCredentialQuery.data?.fallback_enabled)}
              byokExpected={byokExpected}
            />
            {chatPaused && <div id="chat-paused-description" className="chat-paused-banner" role="status">Chat is temporarily disabled. You can keep browsing and editing your conversations. New research runs will return when chat is restored.</div>}
            <Composer onSend={send} busy={chat.busy} onStop={chat.stop} placeholder={draft.text ? "Edit and send again…" : "Ask a follow-up…"} draft={draft} onDraftChange={setDraft} models={models} selectedModel={selectedModel} onModelChange={(model) => void changeModel(model)} disabled={chatPaused} describedBy={chatPaused ? "chat-paused-description" : undefined} paperMentionsEnabled={Boolean(availabilityQuery.data?.paper_mentions_enabled)} webSearchAvailable={webSearchAvailable} webSearchEnabled={webSearchEnabled} onWebSearchChange={setWebSearchEnabled} reasoningEffort={reasoningEffort} onReasoningEffortChange={(effort) => void changeReasoningEffort(effort)} />
            <div className="chat-composer-foot">{isChatLive() ? <>
              {selectedProvider === "openrouter"
                ? <span className="chat-provider-attribution">Powered by <a href="https://openrouter.ai" target="_blank" rel="noreferrer">OpenRouter</a>.</span>
                : <span className="chat-provider-attribution">Powered by 🤗 <a href="https://huggingface.co/docs/inference-providers/en/index" target="_blank" rel="noreferrer">Inference Providers</a>.</span>}
              <span>The AI assistant can make mistakes. Double-check responses.</span>
            </> : <>Assistant preview — responses are simulated.</>}</div>
          </div></div>
        </>}
      </section>
      {manualShareUrl && (
        <div className="chat-share-dialog-backdrop" role="presentation" onMouseDown={() => setManualShareUrl("")}>
          <div
            className="chat-share-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="chat-share-dialog-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <h2 id="chat-share-dialog-title">Public link created</h2>
            <p>
              Anyone with this link can see this conversation. It could not be
              copied automatically, so copy it manually:
            </p>
            <input
              readOnly
              value={manualShareUrl}
              aria-label="Public conversation link"
              autoFocus
              onFocus={(event) => event.currentTarget.select()}
            />
            <button type="button" onClick={() => setManualShareUrl("")}>Close</button>
          </div>
        </div>
      )}
      {chat.capacityRequest && (
        <ChatCapacityDialog
          retryAt={chat.capacityRequest.retryAt}
          onCancel={chat.cancelCapacity}
          onRetry={() => {
            if (chat.retryCapacity()) setDraft(emptyDraft());
          }}
        />
      )}
      {chat.disabledRequest && <ChatDisabledDialog onClose={() => {
        setDraft(chat.disabledRequest?.draft ?? draft);
        chat.dismissDisabled();
        void availabilityQuery.refetch();
      }} />}
    </div>
  );
};

export default ChatView;
