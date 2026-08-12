import { randomUUID } from "node:crypto";
import {
  createAgentSession,
  DefaultResourceLoader,
  type AgentSession,
  SessionManager,
  SettingsManager,
} from "@earendil-works/pi-coding-agent";
import { PiEventAdapter, type PwCEvent } from "./events.js";
import { ANSWER_NOW, PolicyController, pwcExtension } from "./policy.js";
import { createProvider, thinkingLevel } from "./provider.js";
import { renderPrompt } from "./prompt.js";
import { createOrBind, restoreFile, TranscriptMirror } from "./transcript.js";
import { shouldResetSession } from "./session.js";

export interface RunTurn {
  request_id: string;
  chat_session_id: string;
  prompt: string;
  model: string;
  resume: string | null;
  web_search_enabled: boolean;
  reasoning_effort: "low" | "high" | "max";
  hf_username: string;
}

const FINALIZER_PROMPT = `${ANSWER_NOW} Produce only the best concise final answer now.`;

export class PiWorker {
  private session: AgentSession | undefined;
  private manager: SessionManager | undefined;
  private mirror: TranscriptMirror | undefined;
  private mirroredEntryCount = 0;
  private boundChatSession: string | undefined;
  private boundAgentSession: string | undefined;
  private activeRequest: string | undefined;
  private cancelled = false;
  private readonly policy = new PolicyController({
    maximumCalls: Number(process.env.PWC_CHAT_MAX_TOOL_CALLS ?? 12),
    maximumRounds: Number(process.env.PWC_CHAT_MAX_TURNS ?? 8) - 2,
    maximumDirectSearches: Number(process.env.PWC_CHAT_MAX_DIRECT_SEARCH_CALLS ?? 4),
    maximumWebSearches: Number(process.env.PWC_CHAT_MAX_WEB_SEARCH_CALLS ?? 3),
    maximumResultBytes: Number(process.env.PWC_CHAT_TOOL_RESULT_MAX_BYTES ?? 24576),
    maximumTurnOutputBytes: Number(process.env.PWC_CHAT_TURN_TOOL_OUTPUT_MAX_BYTES ?? 98304),
    bashTimeoutSeconds: Number(process.env.PWC_CHAT_BASH_TIMEOUT_SECONDS ?? 30),
  });

  constructor(private readonly emit: (requestId: string, event: PwCEvent) => void) {}

  async cancel(requestId: string): Promise<void> {
    if (requestId !== this.activeRequest || !this.session) return;
    this.cancelled = true;
    await this.session.abort();
  }

  private async sessionManager(run: RunTurn): Promise<{ manager: SessionManager; initialCount: number; created: boolean }> {
    if (this.boundChatSession && this.boundChatSession !== run.chat_session_id) {
      throw new Error("Pi worker session ownership mismatch");
    }
    if (shouldResetSession(this.boundAgentSession, run.resume)) {
      // An edit atomically activates a prepared native fork for the same chat.
      // A retry of an interrupted initial prompt may instead deliberately
      // activate a blank transcript (run.resume is null). Drop only the
      // harness-local state in both cases; the worker stays pinned to the chat.
      this.session?.dispose();
      this.session = undefined;
      this.manager = undefined;
      this.mirror = undefined;
      this.mirroredEntryCount = 0;
      this.boundAgentSession = undefined;
    }
    if (this.manager) {
      return { manager: this.manager, initialCount: this.manager.getEntries().length + 1, created: false };
    }
    if (run.resume) {
      const restored = await restoreFile(run.resume, "/home/pwc-chat/.pi-sessions");
      const manager = SessionManager.open(restored.file, "/home/pwc-chat/.pi-sessions", "/workspace");
      if (manager.getSessionId() !== run.resume || manager.getLeafId() !== restored.snapshot.current_leaf_id) {
        throw new Error("Pi restored session identity mismatch");
      }
      this.manager = manager;
      this.boundAgentSession = run.resume;
      return { manager, initialCount: restored.snapshot.entry_count, created: false };
    }
    const id = randomUUID();
    const manager = SessionManager.create("/workspace", "/home/pwc-chat/.pi-sessions", { id });
    const bound = await createOrBind(id);
    if (bound.agent_session_id !== id || bound.entry_count !== 0) {
      throw new Error("Pi session bind contract mismatch");
    }
    this.manager = manager;
    this.boundAgentSession = id;
    return { manager, initialCount: 0, created: true };
  }

  private async open(run: RunTurn): Promise<void> {
    const state = await this.sessionManager(run);
    const prompt = await renderPrompt({
      model: run.model,
      hfUsername: run.hf_username,
      webSearchEnabled: run.web_search_enabled,
    });
    this.policy.reset(run.web_search_enabled, prompt);
    if (!this.mirror) {
      // The remote count includes the session header; getEntries() contains
      // only tree entries.
      this.mirroredEntryCount = Math.max(0, state.initialCount - 1);
      this.mirror = new TranscriptMirror(
        state.manager.getSessionId(),
        state.initialCount,
        state.manager.getLeafId(),
      );
      if (state.created) {
        const header = state.manager.getHeader();
        if (!header) throw new Error("Pi native session header is missing");
        this.mirror.append(header as unknown as Record<string, unknown>);
        await this.mirror.flush();
      }
    }
    this.session?.dispose();
    const provider = await createProvider(run.model);
    const settings = SettingsManager.inMemory({
      compaction: { enabled: true },
      retry: { enabled: false },
    });
    const loader = new DefaultResourceLoader({
      cwd: "/workspace",
      agentDir: "/home/pwc-chat/.pi-disabled",
      settingsManager: settings,
      noExtensions: true,
      noSkills: true,
      noPromptTemplates: true,
      noThemes: true,
      noContextFiles: true,
      systemPrompt: prompt,
      extensionFactories: [{ name: "pwc-policy", factory: pwcExtension(this.policy), hidden: true }],
    });
    await loader.reload();
    const created = await createAgentSession({
      cwd: "/workspace",
      agentDir: "/home/pwc-chat/.pi-disabled",
      modelRuntime: provider.runtime,
      model: provider.model,
      thinkingLevel: thinkingLevel(run.reasoning_effort),
      tools: ["read", "bash", "search_web"],
      excludeTools: ["edit", "write", "grep", "find", "ls", "ask_question"],
      resourceLoader: loader,
      settingsManager: settings,
      sessionManager: state.manager,
    });
    this.session = created.session;
  }

  private mirrorNativeEntries(): void {
    if (!this.manager || !this.mirror) throw new Error("Pi transcript mirror is unavailable");
    const entries = this.manager.getEntries();
    if (entries.length < this.mirroredEntryCount) {
      throw new Error("Pi native transcript moved backwards");
    }
    for (const entry of entries.slice(this.mirroredEntryCount)) {
      this.mirror.append(entry as unknown as Record<string, unknown>);
    }
    this.mirroredEntryCount = entries.length;
  }

  async run(run: RunTurn): Promise<void> {
    if (this.activeRequest) throw new Error("Pi worker already has an active turn");
    this.activeRequest = run.request_id;
    this.cancelled = false;
    this.boundChatSession ??= run.chat_session_id;
    try {
      this.emit(run.request_id, { type: "worker_ready" });
      await this.open(run);
      if (!this.session || !this.manager || !this.mirror || !this.boundAgentSession) {
        throw new Error("Pi worker failed to initialize");
      }
      const adapter = new PiEventAdapter(false, (kind) => {
        if (kind === "answer") this.policy.observeAnswer();
      });
      const unsubscribe = this.session.subscribe((event) => {
        for (const adapted of adapter.feed(event)) this.emit(run.request_id, adapted);
      });
      this.emit(run.request_id, { type: "_sdk_session", session_id: this.boundAgentSession });
      this.emit(run.request_id, { type: "workspace_ready" });
      let mirrorFailed = false;
      try {
        await this.session.prompt(run.prompt, { expandPromptTemplates: false, source: "interactive" });
        if (this.policy.toolingClosed && !this.policy.answerAfterClose && !this.cancelled) {
          this.session.setActiveToolsByName([]);
          await this.session.prompt(FINALIZER_PROMPT, { expandPromptTemplates: false, source: "extension" });
        }
      } finally {
        unsubscribe();
        try {
          this.mirrorNativeEntries();
          await this.mirror.flush();
        } catch {
          mirrorFailed = true;
        }
      }
      if (this.cancelled) {
        this.emit(run.request_id, { type: "worker_done", status: "stopped" });
        return;
      }
      if (mirrorFailed) {
        this.emit(run.request_id, { type: "_mirror_error" });
        this.emit(run.request_id, { type: "worker_done", status: "complete" });
        return;
      }
      this.emit(run.request_id, {
        type: "_execution_telemetry",
        tool_calls: this.policy.calls,
        tool_rounds_executed: this.policy.rounds,
        direct_search_calls: this.policy.searches,
        web_search_calls: this.policy.webSearches,
        compaction_enabled: true,
      });
      this.emit(run.request_id, { type: "done", finish_reason: "success", followups: [] });
      this.emit(run.request_id, { type: "worker_done", status: "complete" });
    } catch (error) {
      if (this.cancelled) {
        this.emit(run.request_id, { type: "worker_done", status: "stopped" });
      } else {
        this.emit(run.request_id, {
          type: "error",
          code: "gateway_unavailable",
          message: "The research run failed.",
        });
        this.emit(run.request_id, { type: "worker_done", status: "complete" });
      }
    } finally {
      this.activeRequest = undefined;
    }
  }
}
