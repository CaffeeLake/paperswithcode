import type { UserPreferences } from "../api";
import type { ApiRequest } from "../apiTransport";
import { apiRequest } from "./request";

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
}

export const accountApi = new AccountApi(apiRequest);
