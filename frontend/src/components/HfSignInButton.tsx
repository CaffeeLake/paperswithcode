/**
 * "Sign in with Hugging Face" header button.
 *
 * Redirects the browser to `/api/v1/auth/hf/login`, which kicks off the
 * OAuth flow implemented in `backend/routers/auth.py`. The current path
 * (and query string) is round-tripped via `?return_to=` so the user lands
 * back exactly where they started after authorizing.
 */

import React from "react";

import { apiUrl, isAuthDisabled } from "@/lib/apiUrl";

const HF_LOGO_SRC =
  "/hf-logo.svg?v=20260513b";

const HfLogo: React.FC<{ size?: number }> = ({ size = 14 }) => (
  <img
    src={HF_LOGO_SRC}
    alt=""
    width={Math.round((size * 95) / 88)}
    height={size}
    aria-hidden="true"
    draggable={false}
    style={{ display: "block" }}
  />
);

interface HfSignInButtonProps {
  returnTo: string;
  compact?: boolean;
}

export const HfSignInButton: React.FC<HfSignInButtonProps> = ({ returnTo, compact = false }) => {
  if (isAuthDisabled()) return null;

  const handleClick = () => {
    const url = apiUrl(
      `/api/v1/auth/hf/login?return_to=${encodeURIComponent(returnTo)}`,
    );
    window.location.href = url;
  };

  if (compact) {
    return (
      <button
        type="button"
        className="icon-btn"
        aria-label="Sign in with Hugging Face"
        title="Sign in with Hugging Face"
        onClick={handleClick}
      >
        <HfLogo size={16} />
      </button>
    );
  }

  return (
    <button
      type="button"
      className="hf-signin-btn"
      onClick={handleClick}
      aria-label="Sign in with Hugging Face"
    >
      <HfLogo size={18} />
      <span>Sign in</span>
    </button>
  );
};

export default HfSignInButton;
