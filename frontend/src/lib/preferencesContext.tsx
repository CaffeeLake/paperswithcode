/**
 * Account preferences context backed by `/api/v1/me/preferences`.
 *
 * Preferences are stored per HF account on the backend. For signed-in users we
 * fetch them once after auth resolves; guests fall back to the defaults (which
 * means closed-source evaluations are shown). The first preference is
 * `hide_closed_source_evals`, consumed by benchmark and paper evaluation tables.
 */

import React from "react";

import { accountApi, type UserPreferences } from "./api/account";
import { useAuth } from "./authContext";

const DEFAULT_PREFERENCES: UserPreferences = {
  hide_closed_source_evals: false,
};

interface PreferencesContextValue {
  preferences: UserPreferences;
  /** True for signed-in users (preferences are persisted server-side). */
  canPersist: boolean;
  isLoading: boolean;
  setHideClosedSourceEvals: (value: boolean) => Promise<void>;
}

const PreferencesContext = React.createContext<PreferencesContextValue | null>(null);

export const PreferencesProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const { user } = useAuth();
  const [preferences, setPreferences] =
    React.useState<UserPreferences>(DEFAULT_PREFERENCES);
  const [isLoading, setIsLoading] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    if (!user) {
      setPreferences(DEFAULT_PREFERENCES);
      return;
    }
    setIsLoading(true);
    accountApi
      .getPreferences()
      .then((prefs) => {
        if (!cancelled) setPreferences(prefs);
      })
      .catch(() => {
        if (!cancelled) setPreferences(DEFAULT_PREFERENCES);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [user]);

  const setHideClosedSourceEvals = React.useCallback(
    async (value: boolean) => {
      const next: UserPreferences = {
        ...preferences,
        hide_closed_source_evals: value,
      };
      // Optimistic update; revert on failure.
      setPreferences(next);
      if (!user) return;
      try {
        const saved = await accountApi.updatePreferences(next);
        setPreferences(saved);
      } catch {
        setPreferences(preferences);
      }
    },
    [preferences, user],
  );

  const value = React.useMemo<PreferencesContextValue>(
    () => ({
      preferences,
      canPersist: Boolean(user),
      isLoading,
      setHideClosedSourceEvals,
    }),
    [preferences, user, isLoading, setHideClosedSourceEvals],
  );

  return (
    <PreferencesContext.Provider value={value}>
      {children}
    </PreferencesContext.Provider>
  );
};

export function usePreferences(): PreferencesContextValue {
  const ctx = React.useContext(PreferencesContext);
  if (!ctx) {
    throw new Error("usePreferences must be used inside a <PreferencesProvider>");
  }
  return ctx;
}
