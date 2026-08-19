import { mkdirSync } from "node:fs";
import { createAgentSession, DefaultResourceLoader, SessionManager, SettingsManager } from "@earendil-works/pi-coding-agent";
import { type McpStatusSnapshot } from "pi-mcp-adapter";
import { createWebMcpExtension } from "./mcp.js";
import {
  EXCALIDRAW_APP_TOOLS,
  EXCALIDRAW_ENDPOINT,
  EXCALIDRAW_MODEL_TOOLS,
  assessExcalidrawReadiness,
} from "./mcp_app_registry.js";
import { createProvider } from "./provider.js";

process.env.MCP_UI_VIEWER = "none";
process.env.PWC_CHAT_EXCALIDRAW_ENABLED = "true";

const agentDir = "/tmp/pwc-qualify-pi";
mkdirSync(agentDir, { recursive: true });
process.env.PI_CODING_AGENT_DIR = agentDir;

const started = performance.now();
let status: McpStatusSnapshot | undefined;

const settings = SettingsManager.inMemory({
  compaction: { enabled: false },
  retry: { enabled: false },
});
const loader = new DefaultResourceLoader({
  cwd: "/workspace",
  agentDir,
  settingsManager: settings,
  noExtensions: true,
  noSkills: true,
  noPromptTemplates: true,
  noThemes: true,
  noContextFiles: true,
  systemPrompt: "qualify\n",
  extensionFactories: [{
    name: "pwc-exa-mcp",
    factory: createWebMcpExtension(process.execPath, [new URL("./exa_mcp_server.js", import.meta.url).pathname], {
      excalidraw: { url: EXCALIDRAW_ENDPOINT },
      onStatus: (snapshot) => {
        status = snapshot;
      },
    }),
    hidden: true,
  }],
});
await loader.reload();
const provider = await createProvider("qualify-route");
const created = await createAgentSession({
  cwd: "/workspace",
  agentDir,
  modelRuntime: provider.runtime,
  model: provider.model,
  tools: ["read", "bash", "search_web", ...EXCALIDRAW_MODEL_TOOLS],
  resourceLoader: loader,
  settingsManager: settings,
  sessionManager: SessionManager.inMemory("/workspace"),
});
try {
  await created.session.bindExtensions({ mode: "print" });
  created.extensionsResult.runtime.refreshTools();
  const deadline = Date.now() + 20_000;
  while (Date.now() < deadline) {
    const names = created.session.getActiveToolNames();
    const server = status?.servers.find((entry) => entry.name === "excalidraw");
    if (server?.status === "connected" && EXCALIDRAW_MODEL_TOOLS.every((name) => names.includes(name))) {
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
    created.extensionsResult.runtime.refreshTools();
  }
  const names = created.session.getActiveToolNames();
  const server = status?.servers.find((entry) => entry.name === "excalidraw");
  const snapshot = assessExcalidrawReadiness({
    enabled: true,
    serverStatus: server?.status,
    activeTools: names,
    createViewDefinition: created.session.getToolDefinition("create_view") as { parameters?: unknown } | undefined,
    latencyMs: Math.round(performance.now() - started),
  });
  let readMeOk = false;
  if (snapshot.ready) {
    const tool = created.session.getToolDefinition("read_me");
    readMeOk = Boolean(tool?.description);
  }
  const unexpected = names.filter((name) => (EXCALIDRAW_APP_TOOLS as readonly string[]).includes(name));
  process.stdout.write(`${JSON.stringify({
    ready: snapshot.ready && readMeOk && unexpected.length === 0,
    failure_class: unexpected.length ? "connected_incompatible" : snapshot.failure_class,
    registered_tool_names: snapshot.registered_tool_names,
    registered_tool_digest: snapshot.registered_tool_digest,
    registration_latency_ms: snapshot.registration_latency_ms,
    read_me_ok: readMeOk,
    server_status: server?.status ?? "missing",
    server_tool_count: server?.toolCount ?? 0,
  })}\n`);
  process.exitCode = snapshot.ready && readMeOk && unexpected.length === 0 ? 0 : 1;
} finally {
  await created.session.extensionRunner.emit({ type: "session_shutdown", reason: "quit" });
  created.session.dispose();
}
