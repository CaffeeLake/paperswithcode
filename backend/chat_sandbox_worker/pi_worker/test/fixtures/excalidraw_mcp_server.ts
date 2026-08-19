import { McpServer } from "@modelcontextprotocol/server";
import { serveStdio } from "@modelcontextprotocol/server/stdio";
import { pathToFileURL } from "node:url";
import * as z from "zod/v4";

const READ_ME = "Use create_view for visual explanations. Do not expose App-only tools.";

export function createExcalidrawFixtureServer(): McpServer {
  const server = new McpServer({ name: "excalidraw", version: "1.0.0" });
  server.registerTool(
    "read_me",
    {
      title: "Read Excalidraw instructions",
      description: "Read the Excalidraw drawing instructions before create_view.",
      inputSchema: z.object({}).strict(),
    },
    async () => ({ content: [{ type: "text" as const, text: READ_ME }] }),
  );
  server.registerTool(
    "create_view",
    {
      title: "Create Excalidraw view",
      description: "Create an interactive diagram.",
      inputSchema: z.object({ elements: z.string().max(131072) }).strict(),
    },
    async () => ({
      content: [{ type: "text" as const, text: "created" }],
      structuredContent: { checkpointId: "fixture" },
    }),
  );
  for (const name of ["export_to_excalidraw", "save_checkpoint", "read_checkpoint"] as const) {
    server.registerTool(
      name,
      {
        title: name,
        description: "App-only Excalidraw tool",
        inputSchema: z.object({}).strict(),
        _meta: { ui: { visibility: ["app"] } },
      },
      async () => ({ content: [{ type: "text" as const, text: name }] }),
    );
  }
  return server;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const handle = serveStdio(createExcalidrawFixtureServer, {
    legacy: "serve",
    onerror: (error) => console.error(`Excalidraw fixture failed: ${error.message}`),
  });
  for (const signal of ["SIGINT", "SIGTERM"] as const) {
    process.on(signal, () => void handle.close().finally(() => process.exit(0)));
  }
}
