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
    expect(curation.freshAuthMutationDraft()).toMatchObject({
      section: "project_pages",
      endpoint: "/an-endpoint-that-does-not-encode-the-section",
      payload: [],
      options: { method: "PUT" },
    });
  });

  it("resubmits a saved draft only after an explicit resume call", async () => {
    const request = vi
      .fn()
      .mockResolvedValueOnce({ sections: { project_pages: "version-1" } })
      .mockRejectedValueOnce(
        new ApiError(
          new Response(null, { status: 401, statusText: "Unauthorized" }),
          JSON.stringify({ detail: { code: "fresh_auth_required" } }),
        ),
      )
      .mockResolvedValueOnce({ id: 42 });
    const curation = new PaperCurationCoordinator(request, vi.fn());

    await curation.primePaper("42");
    await expect(
      curation.mutatePaper(
        "42",
        "project_pages",
        { project_pages: [{ url: "https://example.com" }] },
        "/papers/42/project-pages",
        { method: "PUT", body: JSON.stringify({ project_pages: [] }) },
      ),
    ).rejects.toMatchObject({ status: 401 });
    expect(request).toHaveBeenCalledTimes(2);

    await expect(curation.resumeFreshAuthMutation()).resolves.toEqual({ id: 42 });
    expect(request).toHaveBeenCalledTimes(3);
    expect(curation.freshAuthMutationDraft()).toBeNull();
  });
});
