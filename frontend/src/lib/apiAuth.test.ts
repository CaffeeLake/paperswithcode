import { describe, expect, it, vi } from "vitest";

import { withStaleAuthNotification } from "./apiAuth";
import { ApiError } from "./apiTransport";

function unauthorized(code?: string): ApiError {
  return new ApiError(
    new Response(null, { status: 401, statusText: "Unauthorized" }),
    JSON.stringify({ detail: code ? { code } : "Not authenticated" }),
  );
}

describe("API auth boundary", () => {
  it("notifies the auth context when a session is stale", async () => {
    const stale = vi.fn();
    window.addEventListener("pwc:auth-stale", stale);

    await expect(
      withStaleAuthNotification(() => Promise.reject(unauthorized())),
    ).rejects.toMatchObject({ status: 401 });

    expect(stale).toHaveBeenCalledOnce();
    window.removeEventListener("pwc:auth-stale", stale);
  });

  it("leaves fresh-auth recovery to the paper-curation boundary", async () => {
    const stale = vi.fn();
    window.addEventListener("pwc:auth-stale", stale);

    await expect(
      withStaleAuthNotification(() =>
        Promise.reject(unauthorized("fresh_auth_required")),
      ),
    ).rejects.toMatchObject({ code: "fresh_auth_required" });

    expect(stale).not.toHaveBeenCalled();
    window.removeEventListener("pwc:auth-stale", stale);
  });
});
