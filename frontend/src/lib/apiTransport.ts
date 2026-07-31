import { getStoredAdminToken } from "./adminAuth";

const LOG_API_REQUESTS = import.meta.env.DEV;

export class ApiError extends Error {
  readonly status: number;
  readonly statusText: string;
  readonly response: string;
  readonly detail: unknown;
  readonly code?: string;

  constructor(response: Response, body: string) {
    super(`API request failed: ${response.status} ${response.statusText}`);
    this.name = "ApiError";
    this.status = response.status;
    this.statusText = response.statusText;
    this.response = body;
    try {
      this.detail = JSON.parse(body)?.detail;
      if (
        typeof this.detail === "object" &&
        this.detail !== null &&
        "code" in this.detail &&
        typeof this.detail.code === "string"
      ) {
        this.code = this.detail.code;
      }
    } catch {
      this.detail = undefined;
    }
  }
}

export async function requestJson<T>(
  baseUrl: string,
  endpoint: string,
  options?: RequestInit,
): Promise<T> {
  const url = `${baseUrl}${endpoint}`;
  if (LOG_API_REQUESTS) console.log(`[API] Requesting: ${url}`);

  try {
    const { headers, ...requestOptions } = options ?? {};
    const method = (requestOptions.method ?? "GET").toUpperCase();
    const defaultCache: RequestCache = method === "GET" ? "default" : "no-store";
    const adminToken = getStoredAdminToken();
    const requestHeaders = new Headers(headers);
    if (!requestHeaders.has("Content-Type")) {
      requestHeaders.set("Content-Type", "application/json");
    }
    if (adminToken && !requestHeaders.has("X-Admin-Token")) {
      requestHeaders.set("X-Admin-Token", adminToken);
    }
    const response = await fetch(url, {
      ...requestOptions,
      cache: requestOptions.cache ?? defaultCache,
      credentials: requestOptions.credentials ?? "include",
      headers: requestHeaders,
    });

    if (LOG_API_REQUESTS) {
      console.log(`[API] Response from ${url}:`, response.status, response.statusText);
    }
    if (!response.ok) {
      const error = new ApiError(response, await response.text());
      console.error("[API] Error response:", error.response);
      throw error;
    }
    if (response.status === 204) return undefined as T;

    const data = await response.json();
    if (LOG_API_REQUESTS) console.log("[API] Success:", data);
    return data;
  } catch (error) {
    console.error(`[API] Request to ${url} failed:`, error);
    throw error;
  }
}
