import { beforeEach, describe, expect, it, vi } from "vitest";

import { papersApi } from "./api/papers";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    statusText: status === 409 ? "Conflict" : "OK",
    headers: { "Content-Type": "application/json" },
  });
}

describe("catalog mutation concurrency", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it("uses the section version loaded when the dialog opened", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ sections: { tasks: "opened-version" } }))
      .mockResolvedValueOnce(jsonResponse({ id: "99001" }));

    await papersApi.primeCurationState("99001", true);
    await papersApi.updateTasks("99001", [1, 2]);

    expect(fetchMock).toHaveBeenCalledTimes(2);
    const mutationOptions = fetchMock.mock.calls[1][1] as RequestInit;
    const headers = new Headers(mutationOptions.headers);
    expect(headers.get("If-Match")).toBe("opened-version");
  });

  it("clears a conflicted attempt and waits for explicit reload and resubmission", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ sections: { tasks: "version-1" } }))
      .mockResolvedValueOnce(
        jsonResponse({ detail: { code: "stale_catalog_version" } }, 409),
      )
      .mockResolvedValueOnce(jsonResponse({ sections: { tasks: "version-2" } }))
      .mockResolvedValueOnce(jsonResponse({ id: "99002" }));
    const conflict = vi.fn();
    window.addEventListener("pwc:catalog-conflict", conflict);

    await papersApi.primeCurationState("99002", true);
    await expect(papersApi.updateTasks("99002", [3])).rejects.toMatchObject({
      status: 409,
    });
    expect(conflict).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);

    await expect(papersApi.updateTasks("99002", [3])).rejects.toThrow(
      "version was not loaded",
    );
    expect(fetchMock).toHaveBeenCalledTimes(2);

    await papersApi.primeCurationState("99002", true);
    await papersApi.updateTasks("99002", [3]);
    const firstMutationHeaders = new Headers(
      (fetchMock.mock.calls[1][1] as RequestInit).headers,
    );
    const secondMutationHeaders = new Headers(
      (fetchMock.mock.calls[3][1] as RequestInit).headers,
    );
    expect(secondMutationHeaders.get("If-Match")).toBe("version-2");
    expect(secondMutationHeaders.get("Idempotency-Key")).not.toBe(
      firstMutationHeaders.get("Idempotency-Key"),
    );

    window.removeEventListener("pwc:catalog-conflict", conflict);
  });
});
