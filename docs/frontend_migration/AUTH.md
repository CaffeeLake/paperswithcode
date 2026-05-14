---
name: backend authentication
overview: Hugging Face OAuth + admin allowlist gate for write endpoints. The frontend header shows a "Sign in with Hugging Face" button (or the user avatar dropdown when signed in); the backend issues an httpOnly session cookie and gates every write endpoint via `require_admin`.
isProject: false
---

# Sign in with Hugging Face (implemented)

## Status

**Shipped.** The header-level "Sign in with Hugging Face" button and the
admin-gated edit dialogs are live. The legacy `X-Admin-Token` header path is
intentionally retained as a CLI/cron fallback.

## TL;DR

- **Identity**: Hugging Face OAuth (Authorization Code, with the regular
  client_secret flavour described at <https://huggingface.co/docs/hub/oauth>).
- **Allowlist**: `PWC_ADMIN_HF_USERNAMES` (comma-separated HF usernames).
- **Session**: signed JWT (HS256) in an `httpOnly` + `Secure` (when HTTPS) +
  `SameSite=Lax` cookie named `pwc_session`.
- **CRON**: unaffected — the workflow scripts hit PostgreSQL directly via
  SQLAlchemy and never touch any HTTP endpoint that requires `require_admin`.

## Backend

Implemented in [backend/routers/auth.py](../../backend/routers/auth.py):

| Method | Path                            | Purpose                                                |
| ------ | ------------------------------- | ------------------------------------------------------ |
| GET    | `/api/v1/auth/hf/login`         | 302 → HF authorize URL with a signed `state` JWT       |
| GET    | `/api/v1/auth/hf/callback`      | Exchange code → set `pwc_session` cookie → 302 back    |
| POST   | `/api/v1/auth/logout`           | Clears the cookie                                      |
| GET    | `/api/v1/auth/me`               | `{username, name, avatar_url, is_admin}` or `401`      |

The session payload is `{sub, username, name, avatar_url, is_admin, exp}`
signed with `PWC_JWT_SECRET`. `is_admin` is set iff `username.lower()` is in
`PWC_ADMIN_HF_USERNAMES` (lowercased).

`require_admin` in [backend/utils/auth.py](../../backend/utils/auth.py)
guards every write endpoint:

1. **Cookie path** — read `pwc_session`, decode the JWT, allow if `is_admin`.
2. **Header fallback** — `X-Admin-Token` matches `PWC_ADMIN_API_TOKEN`.
3. Otherwise → `401 Unauthorized`.

Routers gated: `evaluations`, `papers`, `methods`, `cron`. The legacy
`require_admin_token` is kept in `backend/utils/auth.py` for backwards
compatibility, but no router uses it directly anymore.

## Frontend

- New auth context [frontend/src/lib/authContext.tsx](../../frontend/src/lib/authContext.tsx) — `useAuth()` returns `{user, isLoading, refresh, logout}`. Hits `/auth/me` on mount with `credentials: 'include'`.
- API client [frontend/src/lib/api.ts](../../frontend/src/lib/api.ts) sends `credentials: 'include'` on every request and dispatches a `pwc:auth-stale` window event on `401` so the context can clear local state without a page reload.
- Header components [HfSignInButton.tsx](../../frontend/src/components/HfSignInButton.tsx) and [UserMenu.tsx](../../frontend/src/components/UserMenu.tsx) replace the placeholder profile slot from the design prototype.
- Edit dialogs in [PaperDetailView.tsx](../../frontend/src/views/PaperDetailView.tsx) reveal their trigger buttons via `canEditPaper = user?.is_admin || legacy X-Admin-Token in localStorage`.
- [CronDashboard.tsx](../../frontend/src/pages/CronDashboard.tsx) hides the token-input card when signed in as an HF admin and falls back to the token form otherwise.

## HF OAuth app setup (one-time)

1. Register an OAuth app at <https://huggingface.co/settings/applications/new>
   - **Name**: PapersWithCode
   - **Scopes**: `openid`, `profile`
   - **Redirect URIs** (register all that apply):
     - `https://paperswithcode.co/api/v1/auth/hf/callback`
     - `https://staging.paperswithcode.co/api/v1/auth/hf/callback` (if a staging host exists)
     - `http://localhost:8000/api/v1/auth/hf/callback` (local dev with backend on `:8000`)
     - `http://localhost:5173/api/v1/auth/hf/callback` (local dev when Vite proxies the API)
2. Copy `client_id` and `client_secret` into `backend/keys.env`.
3. Generate a JWT secret: `openssl rand -hex 32`.

## Required env vars (`backend/keys.env`)

```bash
PWC_HF_OAUTH_CLIENT_ID=...
PWC_HF_OAUTH_CLIENT_SECRET=...
PWC_JWT_SECRET=...                         # 32-byte hex
PWC_ADMIN_HF_USERNAMES=nielsrogge          # comma-separated
# Optional, kept as CLI fallback:
PWC_ADMIN_API_TOKEN=...
```

## Rollout commands

Run on the VPS, in order:

```bash
cd /root/python_projects/paperswithcode

git pull origin main
uv sync                                                # installs PyJWT
# Edit backend/keys.env to add the four PWC_HF_OAUTH_* / PWC_JWT_SECRET /
# PWC_ADMIN_HF_USERNAMES entries.
./stop_services.sh && ./start_services.sh

# Smoke tests
curl https://paperswithcode.co/api/v1/auth/me            # → 401 unauthenticated
# Then complete the OAuth round-trip in a browser.
```

## Smoke-test checklist

1. `/api/v1/auth/me` returns `401` unauthenticated, `{username, ..., is_admin: true}` after a successful HF round-trip.
2. The header swaps the "Sign in with Hugging Face" button for the avatar dropdown.
3. Edit dialogs (`Tasks`, `Methods`, `Repositories`, `Evaluations`) appear on `/paper/:arxivId` only for allowlisted users.
4. `POST/PUT/DELETE` requests succeed with the cookie and `401` without it.
5. `POST /api/v1/auth/logout` clears the cookie; subsequent writes `401`.
6. CronDashboard auto-fetches when the HF admin signs in (no token form shown); falls back to the token form when signed out.

## CSRF notes

Relies on `SameSite=Lax` cookies plus a short-lived host-bound `state` JWT on
the OAuth callback. Sufficient for our threat model (single-operator project,
no cross-site embeds). If the threat model changes, layer in a `CSRF-Token`
header on writes.

## Out of scope

- Users DB table — the allowlist stays env-var driven.
- Refresh tokens — 30-day session JWT, user re-logs after expiry.
- Removing the `X-Admin-Token` header path — kept for CLI/cron tooling.
- Org-level scopes (`read-billing`, `read-repos`, etc.).
