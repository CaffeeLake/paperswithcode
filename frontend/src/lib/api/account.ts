import type { ApiRequest } from "../apiTransport";
import { apiRequest } from "./request";
export type { UserPreferences } from "./account.types";
import type { UserPreferences } from "./account.types";
import type { BookmarkIdsResponse, SavedPapersResponse } from "./account.types";

export interface RateLimitPolicy {
  active_pending: number;
  subject_per_hour: number;
  ip_per_hour: number;
}

export class AccountApi {
  constructor(private readonly request: ApiRequest) {}

  getPreferences(): Promise<UserPreferences> {
    return this.request<UserPreferences>("/me/preferences");
  }

  updatePreferences(preferences: UserPreferences): Promise<UserPreferences> {
    return this.request<UserPreferences>("/me/preferences", {
      method: "PUT",
      body: JSON.stringify(preferences),
    });
  }

  getRateLimitPolicy(): Promise<RateLimitPolicy> {
    return this.request("/rate-limits", { credentials: "omit" });
  }

  getBookmarkIds(): Promise<BookmarkIdsResponse> {
    return this.request("/me/bookmarks/ids");
  }

  getBookmarks(): Promise<SavedPapersResponse> {
    return this.request("/me/bookmarks");
  }

  addBookmark(paperId: string | number): Promise<void> {
    return this.request(`/me/bookmarks/${paperId}`, { method: "POST" });
  }

  removeBookmark(paperId: string | number): Promise<void> {
    return this.request(`/me/bookmarks/${paperId}`, { method: "DELETE" });
  }
}

export const accountApi = new AccountApi(apiRequest);
