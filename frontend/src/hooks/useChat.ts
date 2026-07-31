import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import {
  type ChatBlock,
  type ChatBrowserLatencyUpdate,
  type ChatEvent,
  type ChatMessage,
  type ChatPaperHit,
  reportChatLatency,
  streamChat,
} from "@/lib/chat";
import { cancelSession, getSession, toUiMessages } from "@/lib/chatSessions";

const WORKSPACE_STATUS = "Preparing research workspace…";
const WORKSPACE_STATUS_DELAY_MS = 750;

function findLastMatchingIndex<T>(items: T[], predicate: (item: T) => boolean): number {
  for (let index = items.length - 1; index >= 0; index -= 1) {
    if (predicate(items[index])) return index;
  }
  return -1;
}

interface BrowserTiming {
  controller: AbortController;
  submittedAt: number;
  requestId?: string;
  firstVisibleAt?: number;
  streamStartReported: boolean;
  firstVisibleReported: boolean;
  terminalReported: boolean;
}

interface UseChatOptions {
  sessionId: string | null;
  initialModel?: string;
  onSessionId: (id: string) => void;
  onTitle: (title: string) => void;
  onSettled: (sessionId: string | null) => void;
  onInterrupted: (text: string) => void;
}

export function useChat(options: UseChatOptions) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [sessionError, setSessionError] = useState("");
  const busyRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  const preparingTimerRef = useRef<number | null>(null);
  const workspaceStatusStateRef = useRef<"armed" | "shown" | "cleared">("cleared");
  const browserTimingRef = useRef<BrowserTiming | null>(null);
  const messagesRef = useRef<ChatMessage[]>([]);
  const optionsRef = useRef(options);
  const promptRef = useRef("");
  const titleRef = useRef("");
  const idRef = useRef(0);
  const messagesGenerationRef = useRef(0);
  const activeSessionIdRef = useRef(options.sessionId);
  const renderedSessionIdRef = useRef(options.sessionId);
  if (renderedSessionIdRef.current !== options.sessionId) {
    renderedSessionIdRef.current = options.sessionId;
    if (activeSessionIdRef.current !== options.sessionId) {
      messagesGenerationRef.current += 1;
    }
  }
  optionsRef.current = options;
  messagesRef.current = messages;

  useEffect(() => () => {
    if (preparingTimerRef.current !== null) {
      window.clearTimeout(preparingTimerRef.current);
    }
    abortRef.current?.abort();
  }, []);
  useEffect(() => {
    if (!busyRef.current) activeSessionIdRef.current = options.sessionId;
  }, [options.sessionId]);

  const papers = useMemo(() => {
    const map: Record<string, ChatPaperHit> = {};
    for (const message of messages) {
      for (const block of message.blocks ?? []) {
        if (block.kind === "tool") {
          for (const result of block.results ?? []) map[result.route_id] = result;
        }
      }
    }
    return map;
  }, [messages]);

  const nextId = () => `m${++idRef.current}_${Date.now().toString(36)}`;
  const patchLast = (fn: (message: ChatMessage) => ChatMessage) => setMessages((previous) => {
    if (!previous.length) return previous;
    const copy = previous.slice();
    copy[copy.length - 1] = fn(copy[copy.length - 1]);
    return copy;
  });
  const addBlock = (block: ChatBlock) => patchLast((message) => ({ ...message, blocks: [...(message.blocks ?? []), block] }));
  const patchBlock = (match: (block: ChatBlock, index: number, blocks: ChatBlock[]) => boolean, patch: (block: ChatBlock) => ChatBlock) =>
    patchLast((message) => ({ ...message, blocks: (message.blocks ?? []).map((block, index, all) => match(block, index, all) ? patch(block) : block) }));
  const isLastOfKind = (kind: ChatBlock["kind"]) => (block: ChatBlock, index: number, blocks: ChatBlock[]) =>
    block.kind === kind && findLastMatchingIndex(blocks, (candidate) => candidate.kind === kind) === index;

  const clearWorkspaceStatus = (controller: AbortController) => {
    if (abortRef.current !== controller) return;
    if (preparingTimerRef.current !== null) {
      window.clearTimeout(preparingTimerRef.current);
      preparingTimerRef.current = null;
    }
    if (workspaceStatusStateRef.current === "cleared") return;
    const wasShown = workspaceStatusStateRef.current === "shown";
    workspaceStatusStateRef.current = "cleared";
    if (!wasShown) return;
    patchLast((message) => {
      if (message.status !== WORKSPACE_STATUS) return message;
      const { status: _status, ...rest } = message;
      return rest;
    });
  };

  const reportTiming = (
    timing: BrowserTiming,
    update: ChatBrowserLatencyUpdate,
  ) => {
    if (timing.requestId) reportChatLatency(timing.requestId, update);
  };

  const recordStreamStart = (controller: AbortController, requestId: string) => {
    const timing = browserTimingRef.current;
    if (!timing || timing.controller !== controller) return;
    timing.requestId = requestId;
    if (!timing.streamStartReported) {
      timing.streamStartReported = true;
      reportTiming(timing, {
        submission_to_stream_start_ms: Math.max(0, performance.now() - timing.submittedAt),
      });
    }
    if (timing.firstVisibleAt !== undefined && !timing.firstVisibleReported) {
      timing.firstVisibleReported = true;
      reportTiming(timing, {
        submission_to_first_visible_delta_ms: Math.max(
          0,
          timing.firstVisibleAt - timing.submittedAt,
        ),
      });
    }
  };

  const recordTerminal = (
    controller: AbortController,
    classification: NonNullable<ChatBrowserLatencyUpdate["terminal_classification"]>,
  ) => {
    const timing = browserTimingRef.current;
    if (!timing || timing.controller !== controller || timing.terminalReported) return;
    timing.terminalReported = true;
    reportTiming(timing, { terminal_classification: classification });
  };

  useLayoutEffect(() => {
    const timing = browserTimingRef.current;
    if (!timing || timing.firstVisibleAt !== undefined) return;
    const assistant = messages.at(-1);
    if (assistant?.role !== "assistant") return;
    const visible = (assistant.blocks ?? []).some((block) => (
      block.kind === "tool"
      || (block.kind === "reasoning" && Boolean(block.text.trim()))
      || (block.kind === "answer" && Boolean(block.text.trim()))
    ));
    if (!visible) return;
    timing.firstVisibleAt = performance.now();
    if (timing.requestId && !timing.firstVisibleReported) {
      timing.firstVisibleReported = true;
      reportTiming(timing, {
        submission_to_first_visible_delta_ms: Math.max(
          0,
          timing.firstVisibleAt - timing.submittedAt,
        ),
      });
    }
  }, [messages]);

  const applyEvent = (event: ChatEvent) => {
    switch (event.type) {
      case "stream_start":
        if (event.session_id) {
          activeSessionIdRef.current = event.session_id;
          optionsRef.current.onSessionId(event.session_id);
        }
        break;
      case "sandbox_start":
      case "sandbox_ready":
      case "workspace_ready":
        break;
      case "session_title_start":
        titleRef.current = "";
        break;
      case "session_title_delta":
        titleRef.current += event.text;
        optionsRef.current.onTitle(titleRef.current.replace(/\s+/g, " ").slice(0, 80));
        break;
      case "session_title_done":
        titleRef.current = event.title;
        optionsRef.current.onTitle(event.title);
        break;
      case "reasoning_start":
        patchLast((message) => ({
          ...message,
          blocks: [
            ...(message.blocks ?? []).map((block) => block.kind === "reasoning" && block.active
              ? { ...block, active: false, open: false }
              : block),
            { kind: "reasoning", text: "", active: true, open: true },
          ],
        }));
        break;
      case "reasoning_delta":
        patchBlock(isLastOfKind("reasoning"), (block) => block.kind === "reasoning" ? { ...block, text: block.text + event.text } : block);
        break;
      case "reasoning_end":
        patchLast((message) => {
          const blocks = message.blocks ?? [];
          const currentIndex = findLastMatchingIndex(
            blocks,
            (block) => block.kind === "reasoning" && block.active,
          );
          if (currentIndex < 0) return message;
          const current = blocks[currentIndex];
          if (current.kind !== "reasoning") return message;
          const previous = blocks[currentIndex - 1];
          if (previous?.kind === "reasoning" && previous.text === current.text) {
            return {
              ...message,
              blocks: blocks.filter((_block, index) => index !== currentIndex),
            };
          }
          return {
            ...message,
            blocks: blocks.map((block, index) => index === currentIndex
              ? { ...current, active: false, open: false }
              : block),
          };
        });
        break;
      case "tool_call":
        addBlock({ kind: "tool", id: event.id, name: event.name, args: event.args, status: "running", open: false });
        break;
      case "tool_result":
        patchBlock((block) => block.kind === "tool" && block.id === event.id, (block) => block.kind === "tool"
          ? event.status
            ? { ...block, schema_version: 2, status: event.status, took_ms: event.took_ms, content: event.content, metadata: event.metadata, open: event.status !== "success" }
            : { ...block, status: "done", hits: event.hits, took_ms: event.took_ms, results: event.results }
          : block);
        break;
      case "answer_delta":
        patchLast((message) => {
          const blocks = message.blocks ?? [];
          const last = blocks.at(-1);
          if (last?.kind === "answer" && !last.done) return { ...message, blocks: [...blocks.slice(0, -1), { ...last, text: last.text + event.text }] };
          return { ...message, blocks: [...blocks, { kind: "answer", text: event.text, done: false }] };
        });
        break;
      case "done":
        patchLast((message) => ({ ...message, streaming: false, followups: event.followups, finishReason: event.finish_reason, citations: event.citations, blocks: (message.blocks ?? []).map((block) => block.kind === "answer" ? { ...block, done: true } : block.kind === "reasoning" && block.active ? { ...block, active: false, open: false } : block) }));
        break;
      case "error":
        patchLast((message) => ({
          ...message,
          streaming: false,
          error: event.message,
          errorCode: event.code,
          blocks: (message.blocks ?? []).map((block) => block.kind === "reasoning" && block.active
            ? { ...block, active: false, open: false }
            : block),
        }));
        break;
    }
  };

  const reloadCanonical = async (sessionId: string, generation: number) => {
    const detail = await getSession(sessionId);
    const restored = toUiMessages(detail);
    if (messagesGenerationRef.current !== generation) return null;
    setMessages(restored);
    messagesRef.current = restored;
    return restored;
  };

  interface EditRequest {
    targetId: string;
    snapshot: ChatMessage[];
    first: boolean;
  }

  const run = (
    question: string,
    request: Parameters<typeof streamChat>[0],
    optimistic: ChatMessage[],
    edit?: EditRequest,
  ) => {
    const messagesGeneration = ++messagesGenerationRef.current;
    busyRef.current = true;
    const controller = new AbortController();
    abortRef.current = controller;
    promptRef.current = question;
    activeSessionIdRef.current = request.session_id;
    setSessionError("");
    setMessages(optimistic);
    setBusy(true);
    browserTimingRef.current = {
      controller,
      submittedAt: performance.now(),
      streamStartReported: false,
      firstVisibleReported: false,
      terminalReported: false,
    };
    if (preparingTimerRef.current !== null) {
      window.clearTimeout(preparingTimerRef.current);
    }
    workspaceStatusStateRef.current = "armed";
    preparingTimerRef.current = window.setTimeout(() => {
      preparingTimerRef.current = null;
      if (
        abortRef.current !== controller
        || controller.signal.aborted
        || messagesGenerationRef.current !== messagesGeneration
      ) return;
      workspaceStatusStateRef.current = "shown";
      patchLast((message) => (
        message.role === "assistant"
        && message.streaming
        && (message.blocks?.length ?? 0) === 0
        && !message.error
          ? { ...message, status: WORKSPACE_STATUS }
          : message
      ));
    }, WORKSPACE_STATUS_DELAY_MS);
    void (async () => {
      let sawStreamStart = false;
      let sawTerminalEvent = false;
      let streamFailed = false;
      try {
        for await (const event of streamChat(request, { signal: controller.signal })) {
          if (event.type === "stream_start") {
            sawStreamStart = true;
            recordStreamStart(controller, event.request_id);
          }
          if (
            event.type === "workspace_ready"
            || event.type === "reasoning_start"
            || event.type === "reasoning_delta"
            || event.type === "tool_call"
            || event.type === "answer_delta"
            || event.type === "done"
            || event.type === "error"
          ) {
            clearWorkspaceStatus(controller);
          }
          if (event.type === "done" || event.type === "error") {
            sawTerminalEvent = true;
            streamFailed = event.type === "error";
            recordTerminal(controller, event.type === "error" ? "error" : "complete");
          }
          if (!controller.signal.aborted) applyEvent(event);
        }
      } catch (error) {
        streamFailed = true;
        if (!controller.signal.aborted) {
          clearWorkspaceStatus(controller);
          recordTerminal(controller, "network_error");
          applyEvent({ type: "error", message: error instanceof Error ? error.message : "The assistant stream failed." });
        }
      } finally {
        if (abortRef.current === controller) {
          clearWorkspaceStatus(controller);
          if (!sawTerminalEvent && !controller.signal.aborted) {
            recordTerminal(controller, "network_error");
          }
          busyRef.current = false;
          setBusy(false);
          if (!controller.signal.aborted) {
            const canonicalId = activeSessionIdRef.current;
            if (edit && !sawStreamStart) {
              setMessages(edit.snapshot);
              messagesRef.current = edit.snapshot;
              setSessionError("Couldn’t resend this message. Your original conversation was restored.");
            } else if (canonicalId) {
              if (edit && !edit.first && (streamFailed || !sawTerminalEvent)) {
                setMessages(edit.snapshot);
                messagesRef.current = edit.snapshot;
              }
              try {
                const canonical = await reloadCanonical(canonicalId, messagesGeneration);
                if (
                  canonical && edit
                  && !edit.first
                  && canonical.some((message) => message.id === edit.targetId)
                ) {
                  setSessionError("Couldn’t resend this message. Your original conversation was restored.");
                }
              } catch {
                if (messagesGenerationRef.current === messagesGeneration) {
                  patchLast((message) => message.streaming ? { ...message, streaming: false } : message);
                }
              }
            } else {
              patchLast((message) => message.streaming ? { ...message, streaming: false } : message);
            }
            optionsRef.current.onSettled(canonicalId);
          }
          if (browserTimingRef.current?.controller === controller) {
            browserTimingRef.current = null;
          }
        }
      }
    })();
    return true;
  };

  const send = useCallback((text: string) => {
    const question = text.trim();
    if (!question || question.length > 8_000 || busyRef.current) return false;
    const current = messagesRef.current;
    const latestUser = [...current].reverse().find((message) => message.role === "user");
    const replacement = latestUser?.status && latestUser.status !== "complete" && latestUser.revision
      ? { replace_message_id: latestUser.id, prior_revision: latestUser.revision }
      : null;
    const nextUser: ChatMessage = { id: nextId(), role: "user", text: question };
    const nextAssistant: ChatMessage = { id: nextId(), role: "assistant", streaming: true, blocks: [] };
    const replaceIndex = replacement && latestUser
      ? findLastMatchingIndex(current, (message) => message.id === latestUser.id)
      : -1;
    const optimistic = replaceIndex < 0
      ? [...current, nextUser, nextAssistant]
      : [...current.slice(0, replaceIndex), nextUser, nextAssistant];
    return run(question, {
      message: question,
      session_id: optionsRef.current.sessionId,
      client_message_id: crypto.randomUUID(),
      ...(!optionsRef.current.sessionId && optionsRef.current.initialModel ? { initial_model: optionsRef.current.initialModel } : {}),
      ...(replacement ?? {}),
    }, optimistic);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const editAndResend = useCallback((messageId: string, text: string) => {
    const question = text.trim();
    if (!question || question.length > 8_000 || busyRef.current) return false;
    const snapshot = messagesRef.current.slice();
    const targetIndex = snapshot.findIndex(
      (message) => message.id === messageId && message.role === "user",
    );
    if (targetIndex < 0) return false;
    const target = snapshot[targetIndex];
    const firstUserIndex = snapshot.findIndex((message) => message.role === "user");
    const first = targetIndex === firstUserIndex;
    if (!first && (!optionsRef.current.sessionId || !target.revision)) return false;
    const nextUser: ChatMessage = {
      id: target.id,
      role: "user",
      text: question,
      revision: first ? undefined : target.revision! + 1,
      status: "generating",
    };
    const nextAssistant: ChatMessage = {
      id: nextId(),
      role: "assistant",
      streaming: true,
      blocks: [],
    };
    const optimistic = first
      ? [nextUser, nextAssistant]
      : [...snapshot.slice(0, targetIndex), nextUser, nextAssistant];
    return run(question, {
      message: question,
      session_id: first ? null : optionsRef.current.sessionId,
      client_message_id: crypto.randomUUID(),
      ...(first && optionsRef.current.initialModel ? { initial_model: optionsRef.current.initialModel } : {}),
      ...(!first ? {
        replace_message_id: target.id,
        prior_revision: target.revision!,
      } : {}),
    }, optimistic, {
      targetId: target.id,
      snapshot,
      first,
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const stop = useCallback(() => {
    if (!abortRef.current) return;
    const controller = abortRef.current;
    clearWorkspaceStatus(controller);
    recordTerminal(controller, "stopped");
    controller.abort();
    abortRef.current = null;
    if (browserTimingRef.current?.controller === controller) {
      browserTimingRef.current = null;
    }
    busyRef.current = false;
    setBusy(false);
    setMessages((previous) => {
      const last = previous.at(-1);
      if (last?.role !== "assistant") return previous;
      const completed = (last.blocks ?? []).flatMap((block): ChatBlock[] => {
        if (block.kind === "tool" && block.status === "running") return [];
        if (block.kind === "reasoning" && block.active) return [];
        if (block.kind === "answer") return [{ ...block, done: true }];
        return [block];
      });
      return [
        ...previous.slice(0, -1),
        { ...last, blocks: completed, streaming: false, finishReason: "stopped" },
      ];
    });
    optionsRef.current.onInterrupted(promptRef.current);
    const sessionId = activeSessionIdRef.current;
    if (sessionId) void cancelSession(sessionId).catch(() => undefined);
    const messagesGeneration = ++messagesGenerationRef.current;
    window.setTimeout(() => {
      if (sessionId && messagesGenerationRef.current === messagesGeneration) {
        void reloadCanonical(sessionId, messagesGeneration)
        .catch(() => undefined)
        .finally(() => optionsRef.current.onSettled(sessionId));
      } else if (!sessionId) {
        optionsRef.current.onSettled(null);
      }
    }, 450);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const toggleBlock = useCallback((messageId: string, blockIndex: number) => setMessages((previous) => previous.map((message) => message.id !== messageId ? message : { ...message, blocks: message.blocks?.map((block, index) => index === blockIndex && (block.kind === "reasoning" || block.kind === "tool") ? { ...block, open: !block.open } : block) })), []);
  const reset = useCallback(() => {
    messagesGenerationRef.current += 1;
    if (preparingTimerRef.current !== null) {
      window.clearTimeout(preparingTimerRef.current);
      preparingTimerRef.current = null;
    }
    workspaceStatusStateRef.current = "cleared";
    abortRef.current?.abort();
    abortRef.current = null;
    browserTimingRef.current = null;
    busyRef.current = false;
    activeSessionIdRef.current = null;
    setMessages([]);
    setBusy(false);
    setSessionError("");
  }, []);
  const load = useCallback((restored: ChatMessage[]) => {
    messagesGenerationRef.current += 1;
    if (preparingTimerRef.current !== null) {
      window.clearTimeout(preparingTimerRef.current);
      preparingTimerRef.current = null;
    }
    workspaceStatusStateRef.current = "cleared";
    abortRef.current?.abort();
    abortRef.current = null;
    browserTimingRef.current = null;
    busyRef.current = false;
    setMessages(restored);
    setBusy(false);
    setSessionError("");
  }, []);

  return { messages, busy, papers, sessionError, send, editAndResend, stop, toggleBlock, reset, load };
}
