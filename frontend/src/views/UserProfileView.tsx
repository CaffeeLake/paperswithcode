import { useQuery } from "@tanstack/react-query";
import { Navigate, useParams } from "react-router-dom";

import { apiUrl } from "@/lib/apiUrl";
import type { OrganizationContributions } from "@/lib/api";
import { ContributionGraphContent } from "@/components/OrganizationContributionGraph";

interface ProfileResponse {
  username: string;
  redirected_from_alias: boolean;
  calendar: OrganizationContributions;
  is_owner: boolean;
  submissions: Array<{
    id: number;
    edit_type: string;
    status: string;
    proposed_payload: Record<string, unknown>;
    applied_payload?: Record<string, unknown> | null;
    review_reason?: string | null;
    created_at: string;
  }>;
}

async function loadProfile(username: string): Promise<ProfileResponse> {
  const response = await fetch(apiUrl(`/api/v1/profiles/${encodeURIComponent(username)}`), {
    credentials: "include",
  });
  if (!response.ok) throw new Error("Profile not found");
  const data = await response.json() as ProfileResponse;
  if (response.redirected) {
    const canonical = decodeURIComponent(new URL(response.url).pathname.split("/").pop() || data.username);
    return { ...data, username: canonical, redirected_from_alias: true };
  }
  return data;
}

const UserProfileView = () => {
  const { username = "" } = useParams();
  const query = useQuery({
    queryKey: ["user-profile", username.toLowerCase()],
    queryFn: () => loadProfile(username),
  });
  if (query.isLoading) return <div className="page">Loading profile…</div>;
  if (!query.data) return <div className="page"><h1>Profile not found</h1></div>;
  if (query.data.redirected_from_alias) {
    return <Navigate to={`/${query.data.username}`} replace />;
  }
  return (
    <div className="page" style={{ maxWidth: 960 }}>
      <h1>@{query.data.username}</h1>
      <p>Canonical Papers with Code contributions</p>
      <ContributionGraphContent
        data={query.data.calendar}
        organizationName={`@${query.data.username}`}
        title="Canonical contributions"
        noun="contribution"
      />
      {query.data.is_owner && (
        <section className="mt-10">
          <h2>Your submissions</h2>
          <p className="text-sm text-muted-foreground">
            Limits and duplicate behavior are documented on <a href="/rate-limits">the policy page</a>.
          </p>
          <div className="mt-4 space-y-3">
            {query.data.submissions.map((submission) => (
              <article key={submission.id} className="rounded-md border p-4">
                <strong>{submission.edit_type}</strong> · {submission.status}
                <details className="mt-2 text-xs">
                  <summary>Original and applied payload</summary>
                  <pre>{JSON.stringify({ proposed: submission.proposed_payload, applied: submission.applied_payload }, null, 2)}</pre>
                </details>
                {submission.review_reason && <p>{submission.review_reason}</p>}
              </article>
            ))}
          </div>
        </section>
      )}
    </div>
  );
};

export default UserProfileView;
