import type { ExtensionFactory } from "@earendil-works/pi-coding-agent";
import { createMcpAdapter } from "pi-mcp-adapter";
import { EXCALIDRAW_ENDPOINT, EXCALIDRAW_MODEL_TOOLS, excalidrawEnabled } from "./mcp_app_registry.js";

export function createWebMcpExtension(
  command = process.execPath,
  args = [new URL("./exa_mcp_server.js", import.meta.url).pathname],
): ExtensionFactory {
  const excalidraw = excalidrawEnabled();
  const adapter = createMcpAdapter({
    config: {
      mcpServers: {
        exa: {
          command,
          args,
          lifecycle: "lazy",
          directTools: ["search_web"],
          toolPrefix: "none",
          includeTools: ["search_web"],
          exposeResources: false,
          requestTimeoutMs: 4_000,
        },
        ...(excalidraw ? {
          excalidraw: {
            // The adapter owns only model-visible calls.  Its built-in viewer
            // is loopback-only inside Modal and must never be projected.
            url: EXCALIDRAW_ENDPOINT,
            lifecycle: "lazy",
            directTools: [...EXCALIDRAW_MODEL_TOOLS],
            toolPrefix: "none",
            includeTools: [...EXCALIDRAW_MODEL_TOOLS],
            exposeResources: false,
            requestTimeoutMs: 12_000,
          },
        } : {}),
      },
      settings: {
        disableProxyTool: true,
        hostConfigDiscovery: "off",
        mcpFooterStatus: "off",
        notifyOnStartupConnect: false,
        outputGuard: { maxBytes: 24_576, maxLines: 2_000, detailsMaxBytes: 16_384 },
        sampling: false,
        elicitation: false,
        scriptMode: false,
        showStatusIcon: false,
      },
    },
  });
  return (pi) => {
    const previous = process.env.MCP_DIRECT_TOOLS;
    process.env.MCP_DIRECT_TOOLS = ["exa/search_web", ...(excalidraw ? EXCALIDRAW_MODEL_TOOLS.map((tool) => `excalidraw/${tool}`) : [])].join(",");
    try {
      adapter(pi);
    } finally {
      if (previous === undefined) delete process.env.MCP_DIRECT_TOOLS;
      else process.env.MCP_DIRECT_TOOLS = previous;
    }
  };
}
