import type { ApiRequest } from "../apiTransport";
import { apiRequest } from "./request";

export interface UserPreferences {
  /** Hide closed-source model rows on evaluation tables. */
  hide_closed_source_evals: boolean;
}

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
}

export const accountApi = new AccountApi(apiRequest);
