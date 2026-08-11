import React from "react";
import { CheckCircle2 } from "lucide-react";

import HfSignInButton from "@/components/HfSignInButton";
import { apiUrl } from "@/lib/apiUrl";
import { useAuth } from "@/lib/authContext";

const StagingAccessRequestView: React.FC = () => {
  const { user, isLoading } = useAuth();
  const [submitted, setSubmitted] = React.useState(false);
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch(apiUrl("/api/v1/staging-access-request"), {
        method: "POST",
        credentials: "include",
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null) as { detail?: string } | null;
        throw new Error(body?.detail || "Could not submit your request. Please try again.");
      }
      setSubmitted(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not submit your request.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="access-request-page">
      <section className="access-request-card" aria-labelledby="access-request-title">
        <a className="access-request-brand" href="https://paperswithcode.co">
          <span className="brand-mark" aria-hidden="true" />
          <span className="brand-name">Papers <em>with</em> Code</span>
        </a>

        {submitted ? (
          <div className="access-request-success" role="status">
            <CheckCircle2 size={34} strokeWidth={1.6} aria-hidden="true" />
            <h1 id="access-request-title">Request received</h1>
            <p>
              Thanks, @{user?.username}. We’ll review your contributor access request.
            </p>
          </div>
        ) : (
          <>
            <div className="access-request-heading">
              <p className="access-request-eyebrow">Staging preview</p>
              <h1 id="access-request-title">Request access</h1>
              <p>
                This preview is limited to project contributors. Send us your verified
                Hugging Face username and email address to request access.
              </p>
            </div>

            {isLoading ? (
              <p className="access-request-status" role="status">Checking your Hugging Face account…</p>
            ) : user ? (
              <form className="access-request-form" onSubmit={submit}>
                <label htmlFor="hf-username">Hugging Face username</label>
                <div className="access-request-input-wrap">
                  <span aria-hidden="true">@</span>
                  <input
                    id="hf-username"
                    name="hf_username"
                    value={user.username}
                    readOnly
                    autoComplete="username"
                  />
                </div>
                <p className="access-request-verified">
                  Username and email verified through Hugging Face sign-in. See our{" "}
                  <a href="https://paperswithcode.co/privacy">Privacy Policy</a>.
                </p>
                {error && <p className="access-request-error" role="alert">{error}</p>}
                <button className="access-request-submit" type="submit" disabled={submitting}>
                  {submitting ? "Sending…" : "Request access"}
                </button>
              </form>
            ) : (
              <div className="access-request-signin">
                <p>Sign in first so we can verify the account you’re requesting access for.</p>
                <HfSignInButton
                  returnTo="/request-access"
                  label="Sign in with Hugging Face"
                  collectEmail
                />
              </div>
            )}
          </>
        )}
      </section>
    </main>
  );
};

export default StagingAccessRequestView;
