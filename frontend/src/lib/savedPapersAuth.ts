import { authUrl } from "./apiUrl";

export const SAVED_PAPERS_AUTHORIZED_PARAM = "saved_papers_authorized";

export function savedPapersAuthorizationUrl(resumeBookmark = false): string {
  const endpoint = authUrl("/api/v1/auth/hf/login");
  const endpointOrigin = new URL(endpoint, window.location.origin).origin;
  const returnUrl = new URL(window.location.href);
  if (resumeBookmark) {
    returnUrl.searchParams.set(SAVED_PAPERS_AUTHORIZED_PARAM, "1");
  }
  const returnTo =
    endpointOrigin === window.location.origin
      ? `${returnUrl.pathname}${returnUrl.search}${returnUrl.hash}`
      : returnUrl.toString();
  const params = new URLSearchParams({
    return_to: returnTo,
    authorize_bucket: "true",
    bucket_create: "true",
  });
  return `${endpoint}?${params.toString()}`;
}
