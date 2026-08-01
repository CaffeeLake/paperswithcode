/**
 * Account settings view (`/settings`).
 *
 * Houses display preferences and the user-funded Hugging Face Inference
 * Providers connection used by research chat. Display preferences persist
 * server-side for signed-in users and remain session-local for guests.
 */

import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";

import HfSignInButton from "@/components/HfSignInButton";
import { Switch } from "@/components/ui/switch";
import { apiUrl } from "@/lib/apiUrl";
import { useAuth } from "@/lib/authContext";
import { DEFAULT_SITE_SUFFIX, formatPageTitle } from "@/lib/latexPlainText";
import { usePreferences } from "@/lib/preferencesContext";

interface InferenceBillingStatus {
  connected: boolean;
  account_type: string | null;
  monthly_credits_usd: number | null;
  pay_as_you_go: boolean;
  usage_url: string;
  token_url: string;
  bill_to: string | null;
  organizations: Array<{ name: string; display_name: string }>;
}

const SettingsView: React.FC = () => {
  const { user } = useAuth();
  const { preferences, setHideClosedSourceEvals, canPersist } = usePreferences();
  const { theme, setTheme } = useTheme();
  const selectedTheme = theme ?? "system";
  const [billingError, setBillingError] = React.useState("");
  const queryClient = useQueryClient();
  const billingQuery = useQuery({
    queryKey: ["inference-billing", user?.hf_subject],
    enabled: Boolean(user),
    queryFn: async () => {
      const response = await fetch(apiUrl("/api/v1/me/inference-billing"), {
        credentials: "include",
        cache: "no-store",
      });
      if (!response.ok) throw new Error("Could not load billing status.");
      return (await response.json()) as InferenceBillingStatus;
    },
  });
  const billing = billingQuery.data ?? null;
  const selectBillingAccountMutation = useMutation({
    mutationFn: async (billTo: string | null) => {
      const response = await fetch(apiUrl("/api/v1/me/inference-billing"), {
        method: "PATCH",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bill_to: billTo }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(
          typeof payload.detail === "string"
            ? payload.detail
            : "Could not change the billing account.",
        );
      }
      return payload as InferenceBillingStatus;
    },
    onSuccess: (status) => {
      queryClient.setQueryData(["inference-billing", user?.hf_subject], status);
      setBillingError("");
    },
    onError: (error) => {
      setBillingError(
        error instanceof Error ? error.message : "Could not change the billing account.",
      );
    },
  });
  const billingLoading =
    billingQuery.isLoading ||
    selectBillingAccountMutation.isPending;

  React.useEffect(() => {
    document.title = formatPageTitle("Settings");
    return () => {
      document.title = DEFAULT_SITE_SUFFIX;
    };
  }, []);

  return (
    <div className="page">
      <div className="feed-header">
        <div>
          <h1 className="feed-title">
            <em>Settings</em>
          </h1>
          <div className="feed-subtitle">
            Control how papers and benchmarks are displayed across the site.
          </div>
        </div>
      </div>

      <section className="settings-section">
        <h2 className="settings-section-title">Chat usage &amp; billing</h2>
        {!user ? (
          <div className="settings-note settings-note-flush">
            <span>
              Sign in to connect your Hugging Face account for research chat.
              Model usage is billed by Hugging Face, not Papers With Code.
            </span>
            <div className="settings-note-action">
              <HfSignInButton returnTo="/settings" authorizeInference />
            </div>
          </div>
        ) : billingLoading && !billing ? (
          <div className="settings-billing-loading">Checking Hugging Face billing…</div>
        ) : billing?.connected ? (
          <div className="settings-billing">
            <div className="settings-plan-row">
              <div>
                <div className="settings-row-label">
                  {billing.bill_to
                    ? `Hugging Face organization · ${billing.bill_to}`
                    : `Hugging Face ${billing.account_type}`}
                </div>
                <div className="settings-row-desc">
                  {billing.bill_to
                    ? "Chat requests use this organization’s shared credits and billing."
                    : `$${billing.monthly_credits_usd?.toFixed(2)} included each month, then pay as you go through your personal HF account when enabled.`}
                </div>
              </div>
              <span className="settings-connected-badge">Connected</span>
            </div>
            <label className="settings-token-label" htmlFor="hf-billing-account">
              Bill chat usage to
            </label>
            <select
              id="hf-billing-account"
              className="settings-billing-select"
              value={billing.bill_to ?? ""}
              onChange={(event) => {
                setBillingError("");
                selectBillingAccountMutation.mutate(event.target.value || null);
              }}
              disabled={billingLoading}
            >
              <option value="">Personal account (@{user.username})</option>
              {billing.organizations.map((organization) => (
                <option key={organization.name} value={organization.name}>
                  {organization.display_name} ({organization.name})
                </option>
              ))}
            </select>
            <p className="settings-billing-help">
              Hugging Face maintains the authoritative usage, spend, credits, and
              provider limits. Additional usage is billed by Hugging Face when
              pay-as-you-go or purchased credits are enabled.
              Organization billing requires a Team or Enterprise plan and OAuth access
              for the selected organization.
            </p>
            {billingError && <div className="settings-token-error">{billingError}</div>}
            <div className="settings-billing-actions">
              <a
                className="button button-primary"
                href={billing.usage_url}
                target="_blank"
                rel="noreferrer"
              >
                View Hugging Face usage &amp; billing <ExternalLink aria-hidden="true" />
              </a>
              <HfSignInButton
                returnTo="/settings"
                label="Refresh HF permissions"
                authorizeInference
              />
            </div>
          </div>
        ) : (
          <div className="settings-billing-connect">
            <p className="settings-row-desc">
              Authorize Papers With Code to call <strong>Inference Providers</strong>{" "}
              on your behalf. No manually created token is needed. Hugging Face bills
              your personal account by default; after authorizing, you can optionally
              select an eligible organization.
            </p>
            {billingError && <div className="settings-token-error">{billingError}</div>}
            <div className="settings-billing-actions">
              <HfSignInButton
                returnTo="/settings"
                label="Authorize with Hugging Face"
                authorizeInference
              />
            </div>
          </div>
        )}
      </section>

      <section className="settings-section">
        <h2 className="settings-section-title">Appearance</h2>
        <div className="theme-options" aria-label="Color theme">
          {[
            {
              value: "system",
              label: "System",
              description: "Match your device",
              icon: Monitor,
            },
            {
              value: "light",
              label: "Light",
              description: "Always use light mode",
              icon: Sun,
            },
            {
              value: "dark",
              label: "Dark",
              description: "Always use dark mode",
              icon: Moon,
            },
          ].map((option) => {
            const Icon = option.icon;
            const isSelected = selectedTheme === option.value;
            return (
              <button
                key={option.value}
                type="button"
                className={`theme-option ${isSelected ? "is-selected" : ""}`}
                aria-pressed={isSelected}
                onClick={() => setTheme(option.value)}
              >
                <Icon aria-hidden="true" />
                <span className="theme-option-copy">
                  <span className="theme-option-label">{option.label}</span>
                  <span className="theme-option-desc">{option.description}</span>
                </span>
              </button>
            );
          })}
        </div>
      </section>

      <section className="settings-section">
        <h2 className="settings-section-title">Evaluations</h2>
        <div className="settings-row">
          <label className="settings-row-text" htmlFor="hide-closed-source-evals">
            <span className="settings-row-label">Hide closed-source models</span>
            <span className="settings-row-desc">
              When enabled, evaluations of closed-source models (proprietary
              APIs and unreleased flagship models) are hidden from benchmark
              leaderboards and paper result tables.
            </span>
          </label>
          <Switch
            id="hide-closed-source-evals"
            checked={preferences.hide_closed_source_evals}
            onCheckedChange={(checked) => {
              void setHideClosedSourceEvals(Boolean(checked));
            }}
          />
        </div>

        {!canPersist && !user && (
          <div className="settings-note">
            <span>
              You are browsing as a guest, so this choice only applies to the
              current session. Sign in to save it to your account.
            </span>
            <div className="settings-note-action">
              <HfSignInButton returnTo="/settings" />
            </div>
          </div>
        )}
      </section>
    </div>
  );
};

export default SettingsView;
