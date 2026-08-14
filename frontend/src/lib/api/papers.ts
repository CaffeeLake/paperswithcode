import type {
  Paper,
  PaperSearchMode,
  SearchPage,
} from "../api";
import type { ApiRequest } from "../apiTransport";
import { apiRequest } from "./request";

export class PapersApi {
  constructor(private readonly request: ApiRequest) {}

  search(
    query: string,
    page = 1,
    pageSize = 10,
    mode?: PaperSearchMode,
    signal?: AbortSignal,
  ): Promise<SearchPage<Paper>> {
    const searchParams = new URLSearchParams({
      q: query,
      page: page.toString(),
      page_size: pageSize.toString(),
    });
    if (mode) searchParams.set("mode", mode);
    return this.request<SearchPage<Paper>>(
      `/papers/search?${searchParams.toString()}`,
      { signal },
    );
  }

  get(id: string, includeResources = true): Promise<Paper> {
    const query = includeResources ? "?include_resources=true" : "";
    return this.request<Paper>(`/papers/${id}${query}`);
  }

  getByArxivId(arxivId: string, includeResources = true): Promise<Paper> {
    const query = includeResources ? "?include_resources=true" : "";
    return this.request<Paper>(`/papers/arxiv/${arxivId}${query}`);
  }
}

export const papersApi = new PapersApi(apiRequest);
