const ADMIN_TOKEN_STORAGE_KEY = "cronAdminToken";

export function getStoredAdminToken(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(ADMIN_TOKEN_STORAGE_KEY)?.trim() ?? "";
}

export function setStoredAdminToken(token: string): void {
  if (typeof window === "undefined") return;

  const trimmedToken = token.trim();
  if (trimmedToken) {
    window.localStorage.setItem(ADMIN_TOKEN_STORAGE_KEY, trimmedToken);
  } else {
    window.localStorage.removeItem(ADMIN_TOKEN_STORAGE_KEY);
  }
}
