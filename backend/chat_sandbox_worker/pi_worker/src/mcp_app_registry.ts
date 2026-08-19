/** Closed release configuration for browser-hosted MCP Apps.
 *
 * This is deliberately code, not an environment supplied URL or a database
 * row: adding an App means adding a reviewed provider entry and tests.
 */
export const EXCALIDRAW_ENDPOINT = "https://mcp.excalidraw.com/mcp";
export const EXCALIDRAW_RESOURCE_URI = "ui://excalidraw/mcp-app.html";
export const EXCALIDRAW_MODEL_TOOLS = ["read_me", "create_view"] as const;
export const EXCALIDRAW_APP_TOOLS = [
  "export_to_excalidraw",
  "save_checkpoint",
  "read_checkpoint",
] as const;
export const MAX_EXCALIDRAW_ELEMENTS_BYTES = 128 * 1024;
export const MAX_EXCALIDRAW_CONTEXT_BYTES = 8 * 1024;

export interface McpAppProvider {
  id: "excalidraw";
  endpoint: typeof EXCALIDRAW_ENDPOINT;
  resourceUri: typeof EXCALIDRAW_RESOURCE_URI;
  modelTools: readonly (typeof EXCALIDRAW_MODEL_TOOLS)[number][];
  appTools: readonly (typeof EXCALIDRAW_APP_TOOLS)[number][];
}

export const MCP_APP_PROVIDERS: readonly McpAppProvider[] = [{
  id: "excalidraw",
  endpoint: EXCALIDRAW_ENDPOINT,
  resourceUri: EXCALIDRAW_RESOURCE_URI,
  modelTools: EXCALIDRAW_MODEL_TOOLS,
  appTools: EXCALIDRAW_APP_TOOLS,
}];

export function excalidrawEnabled(): boolean {
  return process.env.PWC_CHAT_EXCALIDRAW_ENABLED === "true";
}

export function mcpAppsHostEnabled(): boolean {
  return process.env.PWC_CHAT_MCP_APPS_HOST_ENABLED === "true";
}

export function isExcalidrawModelTool(name: unknown): name is (typeof EXCALIDRAW_MODEL_TOOLS)[number] {
  return typeof name === "string" && (EXCALIDRAW_MODEL_TOOLS as readonly string[]).includes(name);
}
