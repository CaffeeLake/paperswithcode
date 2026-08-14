import type { ExtensionFactory } from "@earendil-works/pi-coding-agent";
import { createMcpAdapter } from "pi-mcp-adapter";

export function createWebMcpExtension(
  command = process.execPath,
  args = [new URL("./exa_mcp_server.js", import.meta.url).pathname],
): ExtensionFactory {
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
    process.env.MCP_DIRECT_TOOLS = "exa/search_web";
    try {
      adapter(pi);
    } finally {
      if (previous === undefined) delete process.env.MCP_DIRECT_TOOLS;
      else process.env.MCP_DIRECT_TOOLS = previous;
    }
  };
}
