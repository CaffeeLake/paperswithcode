import React from "react";
import { AppBridge, PostMessageTransport } from "@modelcontextprotocol/ext-apps/app-bridge";
import type { AppBlock } from "@/lib/chat";
import { appsHostEnabled, excalidrawClient, providerFor } from "./mcpAppRegistry";

const clampHeight = (height: number) => Math.max(240, Math.min(720, height));

export const McpAppFrame: React.FC<{ block: AppBlock }> = ({ block }) => {
  const frame = React.useRef<HTMLIFrameElement>(null);
  const bridge = React.useRef<AppBridge | null>(null);
  const [html, setHtml] = React.useState<string>();
  const [state, setState] = React.useState(block.status);
  const [height, setHeight] = React.useState(clampHeight(block.height));
  const [fullscreen, setFullscreen] = React.useState(false);
  const [attempt, setAttempt] = React.useState(0);

  React.useEffect(() => {
    let cancelled = false;
    const provider = providerFor(block.provider);
    if (!appsHostEnabled() || !provider || block.resource_uri !== provider.resourceUri) {
      setState("unavailable");
      return undefined;
    }
    setState("loading");
    void excalidrawClient().readResource(block.resource_uri).then(({ text }) => {
      if (!cancelled) { setHtml(text); setState(block.status === "error" ? "error" : "ready"); }
    }).catch(() => { if (!cancelled) setState("unavailable"); });
    return () => { cancelled = true; void bridge.current?.teardownResource({}).catch(() => undefined); bridge.current = null; };
  }, [attempt, block.provider, block.resource_uri, block.status]);

  React.useEffect(() => {
    if (!html || !frame.current || state !== "ready") return;
    const current = frame.current;
    const host = new AppBridge(null, { name: "Papers with Code", version: "1" }, {
      serverTools: {}, openLinks: {}, logging: {},
      ...(block.permissions.clipboardWrite ? { clipboard: { write: {} } } : {}),
    }, { hostContext: { theme: document.documentElement.dataset.theme === "dark" ? "dark" : "light", displayMode: fullscreen ? "fullscreen" : "inline" } });
    host.oncalltool = async ({ name, arguments: args }) => {
      if (block.public_fork && name !== "export_to_excalidraw") throw new Error("Shared diagrams cannot mutate owner state");
      return excalidrawClient().callTool(name, (args ?? {}) as Record<string, unknown>) as never;
    };
    host.onopenlink = async ({ url }) => {
      const parsed = new URL(url);
      if (parsed.protocol !== "https:" || parsed.hostname !== "excalidraw.com") throw new Error("External navigation denied");
      if (!window.confirm("This export opens Excalidraw and uploads the diagram to its service. Continue?")) throw new Error("Export cancelled");
      window.open(parsed.href, "_blank", "noopener,noreferrer");
      return {};
    };
    host.onsizechange = ({ height: next }) => { if (typeof next === "number") setHeight(clampHeight(next)); };
    host.oninitialized = () => {
      void host.sendToolInput({ arguments: { elements: JSON.parse(block.input.elements) } });
      void host.sendToolResult(block.result as never);
    };
    bridge.current = host;
    void host.connect(new PostMessageTransport(current.contentWindow ?? undefined, current.contentWindow!)).catch(() => setState("error"));
    return () => { void host.teardownResource({}); bridge.current = null; };
  }, [html, state, fullscreen, block]);

  const unavailable = state === "unavailable" || state === "incompatible" || state === "error";
  return <section className={`chat-mcp-app${fullscreen ? " chat-mcp-app-fullscreen" : ""}`} aria-label="Interactive Excalidraw diagram">
    <header><strong>Visual explanation</strong><span>Experimental · powered by Excalidraw</span><button type="button" onClick={() => setFullscreen((value) => !value)}>{fullscreen ? "Exit fullscreen" : "Fullscreen"}</button></header>
    <p className="chat-mcp-disclosure">Diagram content is processed by the remote Excalidraw MCP service.</p>
    {state === "loading" && <div className="chat-mcp-loading" role="status">Loading interactive diagram…</div>}
    {unavailable && <div className="chat-mcp-error">Interactive diagram unavailable. The cited text answer is still available.<button type="button" onClick={() => setAttempt((value) => value + 1)}>Retry diagram</button></div>}
    {html && state === "ready" && <iframe ref={frame} title="Interactive Excalidraw diagram" sandbox="allow-scripts" allow={block.permissions.clipboardWrite ? "clipboard-write" : undefined} srcDoc={html} style={{ height }} />}
  </section>;
};
