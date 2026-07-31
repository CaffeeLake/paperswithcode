import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, requestJson } from "./apiTransport";

describe("API transport", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns a typed error without applying browser policy", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: { code: "stale_catalog_version" } }), {
        status: 409,
        statusText: "Conflict",
      }),
    );
    const conflict = vi.fn();
    const stale = vi.fn();
    window.addEventListener("pwc:catalog-conflict", conflict);
    window.addEventListener("pwc:auth-stale", stale);

    const result = requestJson("https://example.test", "/unrelated", {
      method: "POST",
    });

    await expect(result).rejects.toEqual(
      expect.objectContaining<ApiError>({
        name: "ApiError",
        message: "API request failed: 409 Conflict",
        status: 409,
        statusText: "Conflict",
        response: JSON.stringify({ detail: { code: "stale_catalog_version" } }),
        detail: { code: "stale_catalog_version" },
        code: "stale_catalog_version",
      }),
    );
    expect(conflict).not.toHaveBeenCalled();
    expect(stale).not.toHaveBeenCalled();
    window.removeEventListener("pwc:catalog-conflict", conflict);
    window.removeEventListener("pwc:auth-stale", stale);
  });

  it("does not notify auth state for unauthorized responses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "Not authenticated" }), {
        status: 401,
        statusText: "Unauthorized",
      }),
    );
    const stale = vi.fn();
    window.addEventListener("pwc:auth-stale", stale);

    await expect(
      requestJson("https://example.test", "/me", { method: "GET" }),
    ).rejects.toMatchObject({ status: 401 });

    expect(stale).not.toHaveBeenCalled();
    window.removeEventListener("pwc:auth-stale", stale);
  });
});
