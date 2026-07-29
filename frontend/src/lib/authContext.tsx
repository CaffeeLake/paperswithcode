/**
 * Auth context backed by the `/api/v1/auth/me` endpoint.
 *
 * The session is held server-side in an httpOnly `pwc_session` cookie set by
 * the HF OAuth callback (see `backend/routers/auth.py`). The frontend simply
 * asks `/auth/me` whether the cookie is valid and caches the result in a
 * React context so any component can read `useAuth()`.
 *
 * A custom `pwc:auth-stale` window event lets the API client (`lib/api.ts`)
 * tell us when a write returned 401 so we can clear local state.
 */

import React from "react";

import { apiUrl, authUrl, isAuthDisabled } from "./apiUrl";

export interface AuthUser {
  username: string;
  name: string | null;
  avatar_url: string | null;
  is_admin: boolean;
  role: "admin" | "contributor" | null;
  can_contribute: boolean;
  can_directly_edit_catalog: boolean;
}

interface AuthContextValue {
  user: AuthUser | null;
  isLoading: boolean;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = React.createContext<AuthContextValue | null>(null);

export const AUTH_STALE_EVENT = "pwc:auth-stale";

async function fetchMe(): Promise<AuthUser | null> {
  if (isAuthDisabled()) return null;
  const res = await fetch(apiUrl("/api/v1/auth/me"), {
    credentials: "include",
    cache: "no-store",
  });
  if (res.status === 401) return null;
  if (!res.ok) return null;
  return (await res.json()) as AuthUser;
}

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = React.useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);

  const refresh = React.useCallback(async () => {
    setIsLoading(true);
    const next = await fetchMe();
    setUser(next);
    setIsLoading(false);
  }, []);

  const logout = React.useCallback(async () => {
    const endpoint = authUrl("/api/v1/auth/logout");
    if (
      new URL(endpoint, window.location.origin).origin !==
      window.location.origin
    ) {
      const form = document.createElement("form");
      form.method = "POST";
      form.action = `${endpoint}?return_to=${encodeURIComponent(window.location.href)}`;
      document.body.appendChild(form);
      form.submit();
      return;
    }
    await fetch(apiUrl("/api/v1/auth/logout"), {
      method: "POST",
      credentials: "include",
    });
    setUser(null);
  }, []);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  React.useEffect(() => {
    const handler = () => setUser(null);
    window.addEventListener(AUTH_STALE_EVENT, handler);
    return () => window.removeEventListener(AUTH_STALE_EVENT, handler);
  }, []);

  const value = React.useMemo<AuthContextValue>(
    () => ({ user, isLoading, refresh, logout }),
    [user, isLoading, refresh, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export function useAuth(): AuthContextValue {
  const ctx = React.useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used inside an <AuthProvider>");
  }
  return ctx;
}
