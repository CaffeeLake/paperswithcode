import React from "react";
import { AppBridge, PostMessageTransport } from "@modelcontextprotocol/ext-apps/app-bridge";
import type { AppBlock } from "@/lib/chat";
import { withCenteredTitle } from "./excalidrawTitle";
import {
  appsHostEnabled,
  excalidrawClient,
  inlineFrameHeight,
  loadExcalidrawAppHtml,
  providerFor,
  resetExcalidrawAppHost,
} from "./mcpAppRegistry";

function whenIframeReady(node: HTMLIFrameElement, connect: () => void): () => void {
  let done = false;
  let innerRaf = 0;
  const run = () => {
    if (done || !node.contentWindow) return;
    done = true;
    connect();
  };
  node.addEventListener("load", run);
  // srcDoc often finishes before React attaches onLoad. A frame callback still
  // sees contentWindow after that missed load event.
  const raf = window.requestAnimationFrame(() => {
    innerRaf = window.requestAnimationFrame(run);
  });
  return () => {
    done = true;
    node.removeEventListener("load", run);
    window.cancelAnimationFrame(raf);
    window.cancelAnimationFrame(innerRaf);
  };
}

export const McpAppFrame: React.FC<{ block: AppBlock }> = ({ block }) => {
  const frame = React.useRef<HTMLIFrameElement>(null);
  const bridge = React.useRef<AppBridge | null>(null);
  const initialized = React.useRef(false);
  const blockRef = React.useRef(block);
  const fullscreenRef = React.useRef(false);
  blockRef.current = block;
  const [html, setHtml] = React.useState<string>();
  const [state, setState] = React.useState<"loading" | AppBlock["status"]>("loading");
  const [height, setHeight] = React.useState(block.height);
  const [fullscreen, setFullscreen] = React.useState(false);
  const [attempt, setAttempt] = React.useState(0);
  const root = React.useRef<HTMLSectionElement>(null);
  const elements = block.input.elements;
  const clipboardWrite = Boolean(block.permissions.clipboardWrite);
  fullscreenRef.current = fullscreen;

  const exitFullscreen = React.useCallback(() => {
    setFullscreen(false);
    if (document.fullscreenElement) void document.exitFullscreen();
  }, []);

  const toggleFullscreen = React.useCallback(() => {
    if (fullscreen) {
      exitFullscreen();
      return;
    }
    setFullscreen(true);
    void root.current?.requestFullscreen?.().catch(() => undefined);
  }, [exitFullscreen, fullscreen]);

  const retry = React.useCallback(() => {
    resetExcalidrawAppHost({ dropHtmlCache: true });
    setHtml(undefined);
    setState("loading");
    setAttempt((value) => value + 1);
  }, []);

  React.useEffect(() => {
    const node = root.current;
    if (!node) return undefined;
    const apply = () => {
      if (fullscreenRef.current) return;
      setHeight(inlineFrameHeight(node.clientWidth));
    };
    apply();
    const observer = new ResizeObserver(apply);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  React.useEffect(() => {
    if (!fullscreen) return;
    const node = root.current;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (document.fullscreenElement) return;
      exitFullscreen();
    };
    const onFullscreenChange = () => {
      if (!document.fullscreenElement) setFullscreen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    document.addEventListener("fullscreenchange", onFullscreenChange);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("fullscreenchange", onFullscreenChange);
      if (document.fullscreenElement === node) void document.exitFullscreen();
    };
  }, [exitFullscreen, fullscreen]);

  React.useEffect(() => {
    let cancelled = false;
    const provider = providerFor(block.provider);
    if (!appsHostEnabled() || !provider || block.resource_uri !== provider.resourceUri) {
      setState("unavailable");
      return undefined;
    }
    setState("loading");
    void loadExcalidrawAppHtml().then((text) => {
      if (!cancelled) {
        setHtml(text);
        setState("ready");
      }
    }).catch(() => { if (!cancelled) setState("unavailable"); });
    return () => { cancelled = true; initialized.current = false; void bridge.current?.teardownResource({}).catch(() => undefined); bridge.current = null; };
  }, [attempt, block.provider, block.resource_uri]);

  React.useEffect(() => {
    if (!html || state !== "ready") return undefined;
    const current = frame.current;
    if (!current) return undefined;
    let host: AppBridge | null = null;
    const cancelReady = whenIframeReady(current, () => {
      if (!current.contentWindow) return;
      host = new AppBridge(null, { name: "Papers with Code", version: "1" }, {
        serverTools: {}, openLinks: {}, logging: {},
        ...(clipboardWrite ? { clipboard: { write: {} } } : {}),
      }, { hostContext: { theme: document.documentElement.dataset.theme === "dark" ? "dark" : "light", displayMode: fullscreen ? "fullscreen" : "inline" } });
      host.oncalltool = async ({ name, arguments: args }) => {
        if (blockRef.current.public_fork && name !== "export_to_excalidraw") throw new Error("Shared diagrams cannot mutate owner state");
        return excalidrawClient().callTool(name, (args ?? {}) as Record<string, unknown>) as never;
      };
      host.onopenlink = async ({ url }) => {
        const parsed = new URL(url);
        if (parsed.protocol !== "https:" || parsed.hostname !== "excalidraw.com") throw new Error("External navigation denied");
        if (!window.confirm("This export opens Excalidraw and uploads the diagram to its service. Continue?")) throw new Error("Export cancelled");
        window.open(parsed.href, "_blank", "noopener,noreferrer");
        return {};
      };
      host.onsizechange = () => undefined;
      host.oninitialized = () => {
        initialized.current = true;
        try {
          const parsed = JSON.parse(elements) as unknown;
          void host!.sendToolInput({
            arguments: { elements: Array.isArray(parsed) ? withCenteredTitle(parsed) : parsed },
          });
          void host!.sendToolResult(blockRef.current.result as never);
        } catch {
          setState("error");
        }
      };
      bridge.current = host;
      void host.connect(new PostMessageTransport(current.contentWindow ?? undefined, current.contentWindow)).catch(() => setState("error"));
    });
    return () => {
      cancelReady();
      initialized.current = false;
      void host?.teardownResource({}).catch(() => undefined);
      if (bridge.current === host) bridge.current = null;
    };
  }, [html, state, fullscreen, elements, clipboardWrite, attempt]);

  React.useEffect(() => {
    if (state !== "ready" || !initialized.current) return;
    void bridge.current?.sendToolResult(block.result as never).catch(() => undefined);
  }, [block.result, state]);

  const unavailable = state === "unavailable" || state === "incompatible" || state === "error";
  return <section ref={root} className={`chat-mcp-app${fullscreen ? " chat-mcp-app-fullscreen" : ""}`} aria-label="Interactive Excalidraw diagram">
    <header>
      <button type="button" onClick={toggleFullscreen}>{fullscreen ? "Exit fullscreen" : "Fullscreen"}</button>
    </header>
    {state === "loading" && <div className="chat-mcp-loading" role="status">Loading interactive diagram…</div>}
    {unavailable && <div className="chat-mcp-error">Interactive diagram unavailable. The cited text answer is still available.<button type="button" onClick={retry}>Retry diagram</button></div>}
    {html && state === "ready" && <iframe key={attempt} ref={frame} title="Interactive Excalidraw diagram" sandbox="allow-scripts" allow={clipboardWrite ? "clipboard-write" : undefined} srcDoc={html} style={{ height }} />}
  </section>;
};
