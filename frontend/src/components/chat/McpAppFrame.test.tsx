import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AppBlock } from "@/lib/chat";

const htmlApi = vi.hoisted(() => ({
  loadExcalidrawAppHtml: vi.fn(),
  resetExcalidrawAppHost: vi.fn(),
  callTool: vi.fn(),
  sendToolInput: vi.fn(async () => {}),
  sendToolResult: vi.fn(async () => {}),
}));

vi.mock("@/components/chat/mcpAppRegistry", () => ({
  appsHostEnabled: () => true,
  providerFor: () => ({ resourceUri: "ui://excalidraw/mcp-app.html" }),
  inlineFrameHeight: (width: number) => (width > 0 ? Math.round(width * 3 / 4) : 525),
  loadExcalidrawAppHtml: htmlApi.loadExcalidrawAppHtml,
  resetExcalidrawAppHost: htmlApi.resetExcalidrawAppHost,
  excalidrawClient: () => ({ callTool: htmlApi.callTool }),
}));

vi.mock("@modelcontextprotocol/ext-apps/app-bridge", () => ({
  AppBridge: class {
    oncalltool?: unknown;
    onopenlink?: unknown;
    onsizechange?: unknown;
    oninitialized?: () => void;
    connect = vi.fn(async () => { this.oninitialized?.(); });
    teardownResource = vi.fn(async () => {});
    sendToolInput = htmlApi.sendToolInput;
    sendToolResult = htmlApi.sendToolResult;
  },
  PostMessageTransport: class {
    constructor() {}
  },
}));

import { McpAppFrame } from "./McpAppFrame";

const block: AppBlock = {
  kind: "app",
  schema_version: 1,
  instance_id: "app-1",
  provider: "excalidraw",
  server: "excalidraw",
  tool: "create_view",
  resource_uri: "ui://excalidraw/mcp-app.html",
  status: "ready",
  input: { elements: '[{"type":"rectangle","id":"box","x":0,"y":0,"width":100,"height":40}]' },
  result: { content: [], structuredContent: {}, isError: false },
  csp: {},
  permissions: { clipboardWrite: true },
  height: 525,
};

describe("McpAppFrame", () => {
  beforeEach(() => {
    htmlApi.loadExcalidrawAppHtml.mockReset();
    htmlApi.resetExcalidrawAppHost.mockReset();
    htmlApi.callTool.mockReset();
    htmlApi.sendToolInput.mockReset();
    htmlApi.sendToolResult.mockReset();
    htmlApi.sendToolInput.mockResolvedValue(undefined);
    htmlApi.sendToolResult.mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders a historical diagram after the App HTML loads", async () => {
    htmlApi.loadExcalidrawAppHtml.mockResolvedValue("<!DOCTYPE html><html><body>diagram</body></html>");
    render(<McpAppFrame block={block} />);
    await waitFor(() => expect(screen.getByTitle("Interactive Excalidraw diagram")).toBeVisible());
    fireEvent.load(screen.getByTitle("Interactive Excalidraw diagram"));
    expect(screen.queryByRole("button", { name: "Retry diagram" })).not.toBeInTheDocument();
  });

  it("injects the scene even if the iframe load event already fired", async () => {
    htmlApi.loadExcalidrawAppHtml.mockResolvedValue("<!DOCTYPE html><html><body>diagram</body></html>");
    Object.defineProperty(HTMLIFrameElement.prototype, "contentWindow", {
      configurable: true,
      get() { return window; },
    });
    try {
      render(<McpAppFrame block={block} />);
      await waitFor(() => expect(htmlApi.sendToolInput).toHaveBeenCalled());
      expect(htmlApi.sendToolInput.mock.calls[0]?.[0]).toEqual({
        arguments: { elements: expect.any(Array) },
      });
    } finally {
      delete (HTMLIFrameElement.prototype as { contentWindow?: Window }).contentWindow;
    }
  });

  it("retries by dropping the cached shell and fetching again", async () => {
    htmlApi.loadExcalidrawAppHtml
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValue("<!DOCTYPE html><html><body>diagram</body></html>");
    render(<McpAppFrame block={{ ...block, status: "error" }} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Retry diagram" })).toBeVisible());
    await userEvent.click(screen.getByRole("button", { name: "Retry diagram" }));
    expect(htmlApi.resetExcalidrawAppHost).toHaveBeenCalledWith({ dropHtmlCache: true });
    await waitFor(() => expect(screen.getByTitle("Interactive Excalidraw diagram")).toBeVisible());
  });
});
