import { describe, expect, it, vi } from "vitest";

import type { UserPreferences } from "../api";
import type { ApiRequest } from "../apiTransport";
import { AccountApi } from "./account";
import { PapersApi } from "./papers";

describe("domain API clients", () => {
  it("encapsulates paper search URL construction", async () => {
    const request = vi.fn().mockResolvedValue({ results: [] }) as ApiRequest;
    const papers = new PapersApi(request);

    await papers.search("vision transformer", 2, 25, "hybrid");

    expect(request).toHaveBeenCalledWith(
      "/papers/search?q=vision+transformer&page=2&page_size=25&mode=hybrid",
      { signal: undefined },
    );
  });

  it("encapsulates account preference mutation payloads", async () => {
    const preferences: UserPreferences = {
      hide_closed_source_evals: true,
    };
    const request = vi.fn().mockResolvedValue(preferences) as ApiRequest;
    const account = new AccountApi(request);

    await account.updatePreferences(preferences);

    expect(request).toHaveBeenCalledWith("/me/preferences", {
      method: "PUT",
      body: JSON.stringify(preferences),
    });
  });
});
