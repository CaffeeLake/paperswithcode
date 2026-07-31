import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Share2, X as XIcon } from "lucide-react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import Composer from "@/components/chat/Composer";
import { AssistantMessage, UserMessage } from "@/components/chat/ChatMessage";
import { PanelIcon, PlusIcon, Spinner, TrashIcon } from "@/components/chat/icons";
import { useToast } from "@/components/ui/use-toast";
import { useChat } from "@/hooks/useChat";
import { isChatLive } from "@/lib/chat";
import {
  CHAT_AUTO_SEND_KEY,
  CHAT_DRAFT_KEY,
  CHAT_MODEL_KEY,
  clearQueuedChatLaunch,
  readQueuedChatLaunch,
} from "@/lib/chatLaunch";
import { SUGGESTED_CHAT_PROMPTS } from "@/lib/chatPrompts";
import { apiUrl, isStagingEnvironment } from "@/lib/apiUrl";
import { useAuth } from "@/lib/authContext";
import {
  DEFAULT_CHAT_MODEL,
  FALLBACK_CHAT_MODELS,
  type ChatModelChoice,
  type ChatSession,
  archiveOldChats,
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
const BILLING_NOTICE_DISMISSED_KEY = "pwc.chat.billing-notice-dismissed.v1";

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
        Hugging Face models require your own HF token. Add it in Settings;
        included monthly credits are used first, then extra usage requires
        purchased credits.
      </span>
      <div className="chat-billing-notice-actions">
        <a href="/settings">Add HF token</a>
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
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [sessionError, setSessionError] = useState("");
  const [routeSessionState, setRouteSessionState] = useState<RouteSessionState | null>(
    () => routeSessionId ? { id: routeSessionId, status: "loading" } : null,
  );
  const [routeLoadAttempt, setRouteLoadAttempt] = useState(0);
  const queuedLaunchRef = useRef(readQueuedChatLaunch());
  const requestedModelRef = useRef(searchParams.get("model") || queuedLaunchRef.current?.model);
  const [models, setModels] = useState<ChatModelChoice[]>(FALLBACK_CHAT_MODELS);
  const [selectedModel, setSelectedModel] = useState(
    requestedModelRef.current || DEFAULT_CHAT_MODEL,
  );
  const selectedProvider = models.find((model) => model.id === selectedModel)?.provider
    ?? "huggingface";
  const staging = isStagingEnvironment();
  const [liveTitle, setLiveTitle] = useState("");
  const [draft, setDraft] = useState("");
  const [pendingAutoPrompt, setPendingAutoPrompt] = useState(
    () => searchParams.get("q")?.trim() || queuedLaunchRef.current?.prompt || "",
  );
  const autoSendStartedRef = useRef(false);
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");
  const [sessionMenu, setSessionMenu] = useState<{ id: string; x: number; y: number } | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(() => typeof window === "undefined" || window.innerWidth > 900);
  const [sharePending, setSharePending] = useState(false);
  const [archivePending, setArchivePending] = useState(false);
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
    onSessionId: (id) => {
      activeStreamSessionIdRef.current = id;
      const isNewSession = id !== routeSessionIdRef.current;
      const shouldFollowStream = routeSessionIdRef.current === activeStreamRouteSessionIdRef.current;
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
    onInterrupted: (text) => {
      setDraft(text);
    },
  });
  const loadChat = chat.load;
  const sendChat = chat.send;

  useEffect(() => {
    if (chat.busy) setEditingMessageId(null);
  }, [chat.busy]);

  const send = useCallback((text: string) => {
    if (!user) {
      sessionStorage.setItem(CHAT_DRAFT_KEY, text);
      sessionStorage.setItem(CHAT_MODEL_KEY, selectedModel);
      sessionStorage.setItem(CHAT_AUTO_SEND_KEY, "1");
      window.location.href = apiUrl(`/api/v1/auth/hf/login?return_to=${encodeURIComponent("/chat")}`);
      return;
    }
    const streamRouteSessionId = routeSessionIdRef.current ?? null;
    if (!sendChat(text)) return;
    activeStreamRouteSessionIdRef.current = streamRouteSessionId;
    activeStreamSessionIdRef.current = streamRouteSessionId;
    clearQueuedChatLaunch();
    setDraft("");
  }, [selectedModel, sendChat, user]);

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
    const savedDraft = sessionStorage.getItem(CHAT_DRAFT_KEY);
    const shouldAutoSend = sessionStorage.getItem(CHAT_AUTO_SEND_KEY) === "1";
    if (savedDraft) {
      if (shouldAutoSend) setPendingAutoPrompt(savedDraft);
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
      chat.load(toUiMessages(detail));
      setSelectedModel(detail.selected_model);
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
    setPendingAutoPrompt(prompt);
    const next = new URLSearchParams(searchParams);
    next.delete("q");
    next.delete("model");
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    if (authLoading || chat.busy || !pendingAutoPrompt || autoSendStartedRef.current) return;
    // Deferring avoids React StrictMode's development-only effect cleanup from
    // aborting the request before the second effect pass can own it.
    const timer = window.setTimeout(() => {
      if (autoSendStartedRef.current) return;
      autoSendStartedRef.current = true;
      const prompt = pendingAutoPrompt;
      setPendingAutoPrompt("");
      send(prompt);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [authLoading, chat.busy, pendingAutoPrompt, send]);

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
    setDraft("");
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
    if (archivePending) return;
    setArchivePending(true);
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
      const failedPrompt = [...chat.messages].reverse().find((message) => message.role === "user")?.text ?? "";
      chat.reset();
      setDraft(failedPrompt);
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
      setArchivePending(false);
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

        {isRouteSessionLoading ? <div className="chat-session-loading" role="status" aria-live="polite">
          <Spinner />
          <span>Loading conversation…</span>
        </div> : routeSessionError ? <div className="chat-session-load-error" role="alert">
          <p>{routeSessionError}</p>
          <button type="button" onClick={() => {
            setRouteSessionState({ id: routeSessionId!, status: "loading" });
            setRouteLoadAttempt((attempt) => attempt + 1);
          }}>Try again</button>
        </div> : isEmpty ? <div className="chat-empty"><div className="chat-empty-inner">
          <div className="chat-empty-eyebrow">AI research assistant · Staging preview</div>
          <h1 className="chat-empty-title">Ask <em>Papers With Code</em></h1>
          <p className="chat-empty-sub">Answers are grounded in a live hybrid search over papers, tasks, and benchmarks — with citations you can follow.</p>
          {staging && <p className="chat-staging-access-note">
            This is a limited staging preview. Only approved Hugging Face users can start chats.
          </p>}
          <BillingNotice provider={selectedProvider} />
          <Composer onSend={send} busy={chat.busy} onStop={chat.stop} autoFocus draft={draft} onDraftChange={setDraft} models={models} selectedModel={selectedModel} onModelChange={(model) => void changeModel(model)} />
          <div className="chat-examples">{SUGGESTED_CHAT_PROMPTS.map((example) => <button type="button" key={example} className="chat-example" onClick={() => send(example)}>{example}</button>)}</div>
        </div></div> : <>
          {chat.sessionError && <div className="chat-session-error" role="alert">{chat.sessionError}</div>}
          <div className="chat-conversation" ref={scrollRef}><div className="chat-conversation-inner">
            {chat.messages.map((message) => message.role === "user"
              ? <UserMessage
                  key={message.id}
                  id={message.id}
                  text={message.text ?? ""}
                  isInitial={message.id === firstUserId}
                  editingAllowed={!chat.busy && Boolean(message.revision)}
                  editing={editingMessageId === message.id}
                  editNotice={message.id === firstUserId
                    ? "Sending will start a new chat."
                    : message.id === latestUserId
                      ? "Sending will replace the response."
                      : "Sending will replace the response and all messages after it."}
                  onEdit={() => setEditingMessageId(message.id)}
                  onCancel={() => setEditingMessageId(null)}
                  onResend={(text) => {
                    if (message.id !== firstUserId) editScrollAnchorRef.current = message.id;
                    const accepted = chat.editAndResend(message.id, text);
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
                  archivePending={archivePending}
                />)}
          </div></div>
          <div className="chat-composer-wrap"><div className="chat-composer-inner">
            <BillingNotice provider={selectedProvider} />
            <Composer onSend={send} busy={chat.busy} onStop={chat.stop} placeholder={draft ? "Edit and send again…" : "Ask a follow-up…"} draft={draft} onDraftChange={setDraft} models={models} selectedModel={selectedModel} onModelChange={(model) => void changeModel(model)} />
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
            <p>It could not be copied automatically. Copy this link manually:</p>
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
    </div>
  );
};

export default ChatView;
