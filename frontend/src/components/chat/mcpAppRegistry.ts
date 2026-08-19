import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import { apiUrl } from "@/lib/apiUrl";

export const EXCALIDRAW_ENDPOINT = "https://mcp.excalidraw.com/mcp";
export const EXCALIDRAW_HOSTNAME = "mcp.excalidraw.com";
export const EXCALIDRAW_HOST_PATH = "/api/v1/chat/mcp-apps/excalidraw";
export const EXCALIDRAW_RESOURCE_URI = "ui://excalidraw/mcp-app.html";
export const EXCALIDRAW_MODEL_TOOLS = ["read_me", "create_view"] as const;
export const EXCALIDRAW_APP_TOOLS = new Set([
  "export_to_excalidraw", "save_checkpoint", "read_checkpoint",
]);
const MAX_APP_CALL_BYTES = 256 * 1024;
const MAX_APP_SESSION_BYTES = 1024 * 1024;

export interface McpAppProvider {
  id: "excalidraw";
  endpoint: typeof EXCALIDRAW_ENDPOINT;
  hostname: typeof EXCALIDRAW_HOSTNAME;
  resourceUri: typeof EXCALIDRAW_RESOURCE_URI;
  modelTools: readonly (typeof EXCALIDRAW_MODEL_TOOLS)[number][];
  appTools: ReadonlySet<string>;
}

export const MCP_APP_PROVIDERS: Readonly<Record<string, McpAppProvider>> = {
  excalidraw: {
    id: "excalidraw", endpoint: EXCALIDRAW_ENDPOINT, hostname: EXCALIDRAW_HOSTNAME,
    resourceUri: EXCALIDRAW_RESOURCE_URI, modelTools: EXCALIDRAW_MODEL_TOOLS,
    appTools: EXCALIDRAW_APP_TOOLS,
  },
};

export function appsHostEnabled(): boolean {
  const value = import.meta.env.VITE_CHAT_MCP_APPS_HOST_ENABLED;
  return value === "true" || value === "1";
}

export function providerFor(value: string): McpAppProvider | undefined {
  return MCP_APP_PROVIDERS[value];
}

export function hostMcpUrl(): URL {
  return new URL(apiUrl(EXCALIDRAW_HOST_PATH), window.location.origin);
}

class BoundedProviderClient {
  private readonly client = new Client({ name: "pwc-chat-mcp-app-host", version: "1" });
  private readonly transport = new StreamableHTTPClientTransport(hostMcpUrl(), {
    requestInit: { credentials: "include" },
  });
  private connected: Promise<void> | undefined;
  private bytes = 0;

  connect(): Promise<void> {
    this.connected ??= this.client.connect(this.transport);
    return this.connected;
  }

  async readResource(uri: string): Promise<{ text: string; digest: string }> {
    if (uri !== EXCALIDRAW_RESOURCE_URI) throw new Error("Unapproved App resource");
    await this.connect();
    const result = await this.client.readResource({ uri });
    const resource = result.contents[0];
    if (!resource || !("text" in resource) || typeof resource.text !== "string" || resource.mimeType !== "text/html;profile=mcp-app") {
      throw new Error("Incompatible App resource");
    }
    this.consume(resource.text, 1024 * 1024);
    const digest = await sha256(resource.text);
    return { text: resource.text, digest };
  }

  async callTool(name: string, args: Record<string, unknown>) {
    if (!EXCALIDRAW_APP_TOOLS.has(name)) throw new Error("Unapproved App tool");
    const body = JSON.stringify(args);
    this.consume(body);
    await this.connect();
    const result = await this.client.callTool({ name, arguments: args });
    this.consume(JSON.stringify(result));
    return result;
  }

  close(): void { void this.transport.close(); }

  private consume(value: string, maximum = MAX_APP_CALL_BYTES): void {
    const bytes = new TextEncoder().encode(value).byteLength;
    if (bytes > maximum || this.bytes + bytes > MAX_APP_SESSION_BYTES) {
      throw new Error("App request exceeds host limit");
    }
    this.bytes += bytes;
  }
}

let providerClient: BoundedProviderClient | undefined;
export function excalidrawClient(): BoundedProviderClient {
  providerClient ??= new BoundedProviderClient();
  return providerClient;
}
export function closeMcpAppClients(): void { providerClient?.close(); providerClient = undefined; }

async function sha256(value: string): Promise<string> {
  const encoded = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", encoded);
  return [...new Uint8Array(digest)].map((part) => part.toString(16).padStart(2, "0")).join("");
}
