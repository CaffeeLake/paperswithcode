import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import {
  createAgentSession,
  DefaultResourceLoader,
  SessionManager,
  SettingsManager,
} from "@earendil-works/pi-coding-agent";
import { createWebMcpExtension } from "../src/mcp.js";
import { createProvider } from "../src/provider.js";

test("Pi exposes only the capability-backed Exa MCP search tool", async () => {
  const agentDir = await mkdtemp(path.join(tmpdir(), "pwc-pi-mcp-"));
  const settings = SettingsManager.inMemory({
    compaction: { enabled: false },
    retry: { enabled: false },
  });
  const server = new URL("../src/exa_mcp_server.ts", import.meta.url).pathname;
  const tsx = new URL("../node_modules/tsx/dist/loader.mjs", import.meta.url).pathname;
  const loader = new DefaultResourceLoader({
    cwd: process.cwd(),
    agentDir,
    settingsManager: settings,
    noExtensions: true,
    noSkills: true,
    noPromptTemplates: true,
    noThemes: true,
    noContextFiles: true,
    systemPrompt: "PwC MCP test prompt\n",
    extensionFactories: [
      {
        name: "pwc-exa-mcp",
        factory: createWebMcpExtension(process.execPath, ["--import", tsx, server]),
        hidden: true,
      },
    ],
  });
  await loader.reload();
  const provider = await createProvider("test-route");
  const created = await createAgentSession({
    cwd: process.cwd(),
    modelRuntime: provider.runtime,
    model: provider.model,
    tools: ["search_web"],
    resourceLoader: loader,
    settingsManager: settings,
    sessionManager: SessionManager.inMemory(process.cwd()),
  });
  try {
    await created.session.bindExtensions({ mode: "print" });
    created.extensionsResult.runtime.refreshTools();
    assert.deepEqual(created.session.getActiveToolNames(), ["search_web"]);
    assert.deepEqual(created.session.getAllTools().map((tool) => tool.name), ["search_web"]);
    assert.match(
      created.session.getToolDefinition("search_web")?.description ?? "",
      /trusted PwC Exa gateway/u,
    );
  } finally {
    await created.session.extensionRunner.emit({ type: "session_shutdown", reason: "quit" });
    created.session.dispose();
    await rm(agentDir, { recursive: true, force: true });
  }
});
