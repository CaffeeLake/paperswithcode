import { describe, expect, it, vi } from "vitest";

import type { UserPreferences } from "../api";
import type { ApiRequest } from "../apiTransport";
import { AccountApi } from "./account";
import { CatalogApi } from "./catalog";
import { EvaluationsApi } from "./evaluations";
import { PapersApi } from "./papers";
import { SubmissionsApi } from "./submissions";

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

  it("keeps catalog filters on the canonical transport", async () => {
    const request = vi.fn().mockResolvedValue({ results: [] }) as ApiRequest;
    const catalog = new CatalogApi(request);

    await catalog.listDatasets({ task_id: 42, include_descendants: true, is_open: false });

    expect(request).toHaveBeenCalledWith(
      "/datasets/?include_descendants=true&is_open=false&task=42",
    );
  });

  it("loads all evaluation pages without changing their ordering", async () => {
    const request = vi.fn()
      .mockResolvedValueOnce({ results: [{ id: "1" }], next_page: 2 })
      .mockResolvedValueOnce({ results: [{ id: "2" }], next_page: null }) as ApiRequest;
    const evaluations = new EvaluationsApi(request);

    await expect(evaluations.byPaper("9")).resolves.toEqual([{ id: "1" }, { id: "2" }]);
    expect(request).toHaveBeenNthCalledWith(
      1,
      "/evaluations/?paper_id=9&ordering=-benchmark_popularity&page_size=100",
      { cache: "no-store" },
    );
    expect(request).toHaveBeenNthCalledWith(
      2,
      "/evaluations/?paper_id=9&ordering=-benchmark_popularity&page=2&page_size=100",
      { cache: "no-store" },
    );
  });

  it("encapsulates pending-review actions", async () => {
    const request = vi.fn().mockResolvedValue({ id: 17 }) as ApiRequest;
    const submissions = new SubmissionsApi(request);

    await submissions.approve(17, { admin_note: "verified" });

    expect(request).toHaveBeenCalledWith("/admin/paper-edits/17/approve", {
      method: "POST",
      body: JSON.stringify({ admin_note: "verified" }),
    });
  });
});
