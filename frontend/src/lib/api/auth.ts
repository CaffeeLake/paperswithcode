import { isAuthDisabled } from "../apiUrl";
import { apiFetch, apiRequest } from "./request";

export interface AuthUser {
  hf_subject: string;
  username: string;
  name: string | null;
  avatar_url: string | null;
  is_admin: boolean;
  role: "admin" | "contributor" | null;
  can_contribute: boolean;
  can_directly_edit_catalog: boolean;
}

export const authApi = {
  async getCurrentUser(): Promise<AuthUser | null> {
    if (isAuthDisabled()) return null;
    const response = await apiFetch("/auth/me", { cache: "no-store" });
    if (response.status === 401 || !response.ok) return null;
    return response.json() as Promise<AuthUser>;
  },

  async logout(): Promise<void> {
    await apiRequest<void>("/auth/logout", { method: "POST" });
  },

  async requestStagingAccess(): Promise<void> {
    await apiRequest<void>("/staging-access-request", { method: "POST" });
  },
};
