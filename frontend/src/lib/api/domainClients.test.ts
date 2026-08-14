import { describe, expect, it, vi } from "vitest";

import type { ApiRequest } from "../apiTransport";
import { AccountApi, type UserPreferences } from "./account";
import { CatalogApi } from "./catalog";
import { ChatApi } from "./chat";
import { EvaluationsApi } from "./evaluations";
import { OperationsApi } from "./operations";
import { PapersApi } from "./papers";
import { profilesApi } from "./profiles";
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
    const preferences: UserPreferences = { hide_closed_source_evals: true };
    const request = vi.fn().mockResolvedValue(preferences) as ApiRequest;
    const account = new AccountApi(request);

    await account.updatePreferences(preferences);

    expect(request).toHaveBeenCalledWith("/me/preferences", {
      method: "PUT",
      body: JSON.stringify(preferences),
    });
  });

  it("makes account policy reads explicitly public", async () => {
    const request = vi.fn().mockResolvedValue({ active_pending: 5 }) as ApiRequest;

    await new AccountApi(request).getRateLimitPolicy();

    expect(request).toHaveBeenCalledWith("/rate-limits", { credentials: "omit" });
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
    const request = vi.fn().mockResolvedValue({
      id: 17,
      paper_id: 9,
      hf_username: "reviewer",
      is_author: false,
      edit_type: "tasks",
      proposed_payload: { task_ids: [2] },
      current_payload: { tasks: [] },
      status: "approved",
      created_at: "2026-08-14T00:00:00Z",
      updated_at: "2026-08-14T00:01:00Z",
    }) as ApiRequest;
    const submissions = new SubmissionsApi(request);

    await submissions.approve(17, { admin_note: "verified" });

    expect(request).toHaveBeenCalledWith("/admin/paper-edits/17/approve", {
      method: "POST",
      body: JSON.stringify({ admin_note: "verified" }),
    });
  });

  it("rejects malformed pending-edit responses at the API boundary", async () => {
    const request = vi.fn().mockResolvedValue({
      count: 1,
      results: [{
        id: 17,
        paper_id: 9,
        hf_username: "reviewer",
        is_author: false,
        edit_type: "tasks",
        proposed_payload: { task_ids: ["bad"] },
        status: "pending",
        created_at: "2026-08-14T00:00:00Z",
        updated_at: "2026-08-14T00:00:00Z",
      }],
    }) as ApiRequest;
    const submissions = new SubmissionsApi(request);

    await expect(submissions.list()).rejects.toThrow(
      "Malformed pending-edit payload: results.0.proposed_payload.task_ids.0",
    );
  });

  it("states chat freshness, public-read, and prewarm policies", async () => {
    const request = vi.fn().mockResolvedValue({}) as ApiRequest;
    const chat = new ChatApi(request);

    await chat.getAvailability();
    await chat.getSharedChat("share/id");
    await chat.prewarmPaperContext("2501.00001");

    expect(request).toHaveBeenNthCalledWith(1, "/chat/availability", { cache: "no-store" });
    expect(request).toHaveBeenNthCalledWith(2, "/chat/shares/share%2Fid", {
      credentials: "omit",
    });
    expect(request).toHaveBeenNthCalledWith(3, "/chat/paper-context/prewarm", {
      method: "POST",
      body: JSON.stringify({ route_id: "2501.00001" }),
      credentials: "omit",
      cache: "no-store",
    });
  });

  it("keeps operations snapshots uncached", async () => {
    const request = vi.fn().mockResolvedValue({}) as ApiRequest;
    const operations = new OperationsApi(request);

    await operations.getCronStatus(true);
    await operations.getPaperMarkdownJobs();

    expect(request).toHaveBeenNthCalledWith(1, "/cron/status?force_refresh=true", {
      cache: "no-store",
    });
    expect(request).toHaveBeenNthCalledWith(2, "/cron/paper-markdown-jobs", {
      cache: "no-store",
    });
  });

  it("preserves the canonical username from profile redirects", async () => {
    const response = new Response(JSON.stringify({
      username: "canonical",
      redirected_from_alias: false,
      calendar: {},
      is_owner: false,
      submissions: [],
    }), { status: 200 });
    Object.defineProperties(response, {
      redirected: { value: true },
      url: { value: "https://example.test/api/v1/profiles/canonical" },
    });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(response);

    await expect(profilesApi.get("old name")).resolves.toMatchObject({
      username: "canonical",
      redirected_from_alias: true,
    });
    expect(String(fetchMock.mock.calls[0][0])).toContain("/profiles/old%20name");
  });
});
