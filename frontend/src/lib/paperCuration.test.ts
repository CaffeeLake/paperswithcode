import { describe, expect, it, vi } from "vitest";

import { ApiError } from "./apiTransport";
import { PaperCurationCoordinator } from "./paperCuration";

describe("paper curation boundary", () => {
  it("recovers fresh authentication using the explicit editor section", async () => {
    const request = vi
      .fn()
      .mockResolvedValueOnce({ sections: { project_pages: "version-1" } })
      .mockRejectedValueOnce(
        new ApiError(
          new Response(null, { status: 401, statusText: "Unauthorized" }),
          JSON.stringify({ detail: { code: "fresh_auth_required" } }),
        ),
      );
    const recoverFreshAuth = vi.fn();
    const curation = new PaperCurationCoordinator(request, recoverFreshAuth);

    await curation.primePaper("42");
    await expect(
      curation.mutatePaper(
        "42",
        "project_pages",
        [],
        "/an-endpoint-that-does-not-encode-the-section",
        { method: "PUT" },
      ),
    ).rejects.toMatchObject({ status: 401 });

    expect(recoverFreshAuth).toHaveBeenCalledWith("project_pages");
  });
});
