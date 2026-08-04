import { afterEach, describe, expect, it, vi } from "vitest";

import { savedPapersAuthorizationUrl } from "./savedPapersAuth";

afterEach(() => {
  vi.unstubAllEnvs();
  window.history.replaceState({}, "", "/");
});

describe("savedPapersAuthorizationUrl", () => {
  it("uses a local return path for same-origin OAuth", () => {
    window.history.replaceState({}, "", "/paper/42?tab=code#results");

    const url = new URL(savedPapersAuthorizationUrl(true), window.location.origin);

    expect(url.searchParams.get("return_to")).toBe(
      "/paper/42?tab=code&saved_papers_authorized=1#results",
    );
    expect(url.searchParams.get("authorize_bucket")).toBe("true");
    expect(url.searchParams.get("bucket_create")).toBe("true");
  });
});
