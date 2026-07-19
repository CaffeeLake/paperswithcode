/**
 * Account settings view (`/settings`).
 *
 * Houses display preferences that used to live in the avatar dropdown. The
 * first (and currently only) preference is `hide_closed_source_evals`, wired to
 * the shared `usePreferences()` context. Signed-in users have their choice
 * persisted server-side; guests can still toggle it for the current session but
 * are nudged to sign in so it sticks.
 */

import React from "react";
import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";

import HfSignInButton from "@/components/HfSignInButton";
import { Switch } from "@/components/ui/switch";
import { useAuth } from "@/lib/authContext";
import { usePreferences } from "@/lib/preferencesContext";
import { DEFAULT_SITE_SUFFIX, formatPageTitle } from "@/lib/latexPlainText";

const SettingsView: React.FC = () => {
  const { user } = useAuth();
  const { preferences, setHideClosedSourceEvals, canPersist } = usePreferences();
  const { theme, setTheme } = useTheme();
  const selectedTheme = theme ?? "system";

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
