import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  EXCALIDRAW_HOST_HTML_PATH,
  inlineFrameHeight,
  loadExcalidrawAppHtml,
  resetExcalidrawAppHost,
} from "./mcpAppRegistry";

describe("inlineFrameHeight", () => {
  it("matches the Excalidraw App 4:3 shell", () => {
    expect(inlineFrameHeight(764)).toBe(573);
    expect(inlineFrameHeight(0)).toBe(525);
    expect(inlineFrameHeight(200)).toBe(240);
    expect(inlineFrameHeight(2000)).toBe(720);
  });
});

describe("loadExcalidrawAppHtml", () => {
  beforeEach(() => {
    resetExcalidrawAppHost({ dropHtmlCache: true });
  });

  afterEach(() => {
    resetExcalidrawAppHost({ dropHtmlCache: true });
    vi.unstubAllGlobals();
  });

  it("caches the App HTML and retries against a fresh request after reset", async () => {
    const html = "<!DOCTYPE html><html><body>diagram</body></html>";
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, text: async () => html })
      .mockResolvedValueOnce({ ok: true, text: async () => html });
    vi.stubGlobal("fetch", fetchMock);

    await expect(loadExcalidrawAppHtml()).resolves.toBe(html);
    await expect(loadExcalidrawAppHtml()).resolves.toBe(html);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain(EXCALIDRAW_HOST_HTML_PATH);

    resetExcalidrawAppHost({ dropHtmlCache: true });
    await expect(loadExcalidrawAppHtml()).resolves.toBe(html);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
