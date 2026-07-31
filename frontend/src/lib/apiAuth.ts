import { ApiError } from "./apiTransport";

export async function withStaleAuthNotification<T>(
  request: () => Promise<T>,
): Promise<T> {
  try {
    return await request();
  } catch (error) {
    if (
      error instanceof ApiError &&
      error.status === 401 &&
      error.code !== "fresh_auth_required" &&
      typeof window !== "undefined"
    ) {
      window.dispatchEvent(new CustomEvent("pwc:auth-stale"));
    }
    throw error;
  }
}
