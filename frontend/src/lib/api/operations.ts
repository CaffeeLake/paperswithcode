import type { CronJobsResponse, PaperMarkdownJobsResponse } from "./operations.types";
export type * from "./operations.types";
import type { ApiRequest } from "../apiTransport";
import { apiRequest } from "./request";

export class OperationsApi {
  constructor(private readonly request: ApiRequest) {}

  getCronStatus(forceRefresh = false): Promise<CronJobsResponse> {
    const query = forceRefresh ? "?force_refresh=true" : "";
    return this.request(`/cron/status${query}`, { cache: "no-store" });
  }

  getPaperMarkdownJobs(): Promise<PaperMarkdownJobsResponse> {
    return this.request("/cron/paper-markdown-jobs", { cache: "no-store" });
  }
}

export const operationsApi = new OperationsApi(apiRequest);
