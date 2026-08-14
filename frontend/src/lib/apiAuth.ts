import { ApiError } from "./apiTransport";

export function notifyStaleAuth(error: unknown): void {
  if (
    error instanceof ApiError &&
    error.status === 401 &&
    error.code !== "fresh_auth_required" &&
    error.code !== "saved_papers_bucket_authorization_required" &&
    typeof window !== "undefined"
  ) {
    window.dispatchEvent(new CustomEvent("pwc:auth-stale"));
  }
}

export async function withStaleAuthNotification<T>(
  request: () => Promise<T>,
): Promise<T> {
  try {
    return await request();
  } catch (error) {
    notifyStaleAuth(error);
    throw error;
  }
}
