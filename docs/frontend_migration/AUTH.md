---
name: backend authentication
overview: GitHub OAuth + admin gate for write endpoints. Carved out of the frontend v2 migration plan ([PLAN.md](PLAN.md)) — implemented as a follow-up workstream after cutover. Until this ships, write endpoints (`POST/PUT/DELETE` on papers/datasets/evaluations/etc.) remain unauthenticated, matching the current production state.
isProject: false
---

# Backend Authentication (deferred — implement after frontend v2 cutover)

## Status

**Not yet implemented.** This was originally part of the v2 migration but was carved out so the frontend can ship sooner. Until this lands, the existing unauthenticated write endpoints stay unauthenticated; admin UI in v2 (edit dialogs, `indexPaperFromArxiv`) ships visible to everyone, matching v1.

When picked up, this is a small self-contained workstream — one new router, one dependency injected onto write endpoints, env-var setup, and matching frontend auth context. No schema work.

## TL;DR

Add real auth on the backend and an admin-gate UI on the frontend.

- **Identity model**: GitHub OAuth + username allowlist (single operator).
- **Token mechanism**: signed JWT (HS256) in an `httpOnly` + `Secure` + `SameSite=Lax` cookie.
- **CRON jobs unaffected** — they bypass HTTP entirely (verified by grep over `.github/workflows/scripts/`).

## Identity model: GitHub OAuth with a username allowlist

- New env vars in `backend/keys.env`:
  - `PWC_GITHUB_OAUTH_CLIENT_ID` — single OAuth App (see "GitHub OAuth App setup" below)
  - `PWC_GITHUB_OAUTH_CLIENT_SECRET`
  - `PWC_JWT_SECRET` — 32-byte random hex used to sign the session JWT and the OAuth `state` JWT
  - `PWC_ADMIN_GITHUB_USERNAMES` — comma-separated allowlist (e.g., `nielsrogge`)

## Backend changes (new `backend/routers/auth.py` and middleware)

- `GET /api/v1/auth/github/login` — generates a short-lived (5 min) `state` JWT containing `{nonce, host}` where `host` is the originating request host (`paperswithcode.co` or `staging.paperswithcode.co`); redirects to GitHub OAuth `authorize` URL with `client_id` + `redirect_uri` (computed from the originating host) + `state` + `scope=read:user`.
- `GET /api/v1/auth/github/callback?code=...&state=...` — verifies the `state` JWT signature and confirms `state.host` matches the incoming request host (CSRF defense without a sessions table); exchanges code for GitHub access token; fetches `/user` to get the username; checks allowlist; issues a signed session JWT; sets it as an `httpOnly` + `Secure` + `SameSite=Lax` cookie named `pwc_admin_session` with `Domain` set to the **originating host** (i.e. `Domain=paperswithcode.co` for prod requests, `Domain=staging.paperswithcode.co` for staging requests — separate cookies per environment).
- `POST /api/v1/auth/logout` — clears the cookie (with the matching `Domain`).
- `GET /api/v1/auth/me` — returns `{username, is_admin: true}` if cookie valid; 401 otherwise.
- New auth dependency `require_admin(request)` injected into every write endpoint (`POST/PUT/DELETE` on papers/datasets/evaluations/etc.).

## Token mechanism

Signed JWT (HS256, secret in `PWC_JWT_SECRET` env var; generate once with `openssl rand -hex 32`). Stateless — no sessions table needed. Expiry: 30 days. No refresh token; user re-logs after expiry (rare event for a single operator). No rotation policy initially; rotating the secret invalidates all existing sessions, which is acceptable.

## CSRF protection

Relies on `SameSite=Lax` cookie behavior + the `state` JWT host check on the OAuth callback — sufficient for our threat model (single operator, no cross-site embeds). No explicit CSRF token header on write endpoints. If the threat model changes, add a CSRF token via `Set-Cookie: csrf-token=...; SameSite=Strict; HttpOnly=false` issued at login + required `X-CSRF-Token` header on writes.

## GitHub OAuth App setup (one-time, manual)

- Create a single OAuth App in GitHub Developer Settings named "PapersWithCode Admin".
- Register **two callback URLs**: `https://paperswithcode.co/api/v1/auth/github/callback` and `https://staging.paperswithcode.co/api/v1/auth/github/callback`.
- Single `client_id` / `client_secret` pair shared by both environments. The backend chooses the correct `redirect_uri` based on the originating request host.

## Cookie scope rationale (separate per environment)

Prod auth is rare and stable; staging auth is frequently broken during dev. A shared `Domain=.paperswithcode.co` cookie would mean every broken staging deploy could invalidate the operator's prod session, and a stale staging JWT could persist into prod after secret rotation. Separate cookies cost nothing and isolate failure modes.

## CORS update (in `backend/config.py`)

- `Settings.cors_allowed_origins` must include `https://staging.paperswithcode.co` regardless of `is_production`. Recommended: introduce a `PWC_ENVIRONMENT=staging` mode that returns `["https://paperswithcode.co", "https://www.paperswithcode.co", "https://staging.paperswithcode.co"]`, and have the staging deploy set that env var. Simpler alternative: unconditionally include staging in the prod list — the only cost is that a leaked staging cert would be acceptable as a CORS origin in prod, which is not a meaningful threat for our setup.
- `allow_credentials=True` is already set in `backend/main.py` — no change needed.

## Frontend changes

- New auth context (React Context, not React Query — auth is global state) holding `{user: User | null, isLoading: boolean, logout: () => void}`. Initial state populated by calling `/api/v1/auth/me` on app mount.
- "Log in with GitHub" button: **only on `/admin/login` route, not in the main header** — admin UI is invisible to non-admin users browsing the site.
- 401 from any write request → clear auth context, redirect to `/admin/login`.
- Edit dialogs and admin-only buttons are conditionally rendered based on `user?.is_admin`.
- API client (`lib/api.ts`) sends `credentials: 'include'` on all fetches so the cookie travels.

## `/admin/login` route

A new route with the v2 header chrome, a centered "Log in with GitHub" button, and (after auth) an "Operator panel" listing the editing entry points. Admin tools elsewhere in the site (edit dialogs on PaperDetailView) are also unlocked by the same auth state.

This route does not exist yet; until this workstream lands, admin UI on PaperDetailView is rendered for everyone (matching the current production state).

## Single-operator allowlist (accepted risk)

`PWC_ADMIN_GITHUB_USERNAMES` will hold a single GitHub username; no second admin, no CLI escape hatch (the operator's GitHub account stability is treated as the source of truth). If that account is ever lost or GitHub OAuth itself breaks, recovery requires SSH-into-VPS + temporarily disabling `require_admin` in code or directly editing the database. Acceptable trade-off given a single-operator project.

## CRON jobs are unaffected by auth

All current CRON jobs (`.github/workflows/scripts/hourly/*.py`, `.github/workflows/scripts/daily/import_hf_daily_papers.py`) call only external APIs (HuggingFace, GitHub, Semantic Scholar) and write to PostgreSQL **directly via SQLAlchemy** — they do not call our own `/api/v1/*` endpoints. Verified by `grep` over `.github/workflows/scripts/`. So no admin bypass key, no service token, no `Authorization` header is required for CRON. The only HTTP write paths that will be gated by `require_admin` are UI-driven (edit dialogs + `indexPaperFromArxiv` from `PaperDetailView`).

## Deferred follow-up: multi-admin support / users table

Current setup is single-operator via the `PWC_ADMIN_GITHUB_USERNAMES` env var. If admin count grows past ~5, or audit logging / role scopes / a UI to manage admins becomes desirable, migrate to a `users` DB table with `github_username`, `is_admin`, `created_at` columns. Out of scope for this auth workstream too; tracked here so it isn't lost.

## Rollout commands (when this workstream is implemented)

Run on the VPS, in order:

```bash
cd /root/python_projects/paperswithcode

# (1) Pull latest code
git pull origin main
uv sync                                                              # install PyJWT, httpx if not already present

# (2) Edit backend/keys.env — add the four new auth env vars:
#       PWC_JWT_SECRET            (generate via: openssl rand -hex 32)
#       PWC_GITHUB_OAUTH_CLIENT_ID
#       PWC_GITHUB_OAUTH_CLIENT_SECRET
#       PWC_ADMIN_GITHUB_USERNAMES

# (3) Restart backend so the new auth router goes live
./stop_services.sh && ./start_services.sh

# (4) Smoke test the auth router
curl https://paperswithcode.co/api/v1/auth/me                        # → 401 unauthenticated
# Then complete the OAuth flow in a browser at https://paperswithcode.co/admin/login
```

## Smoke-test checklist (when implemented)

1. `/admin/login` renders "Log in with GitHub" button; OAuth round-trip succeeds; non-allowlisted users get rejected; allowlisted users land in operator panel.
2. After login, edit dialogs visible on PaperDetailView; PUT/POST/DELETE writes succeed.
3. `GET /api/v1/auth/me` returns `{username, is_admin: true}` with a valid cookie; 401 otherwise.
4. `POST /api/v1/auth/logout` clears the cookie; subsequent writes 401.
5. Cookie has `Domain=paperswithcode.co` on prod requests, `Domain=staging.paperswithcode.co` on staging requests; the two cookies are independent (logging out of staging doesn't log out of prod).
6. State JWT host-check rejects callbacks where the `state.host` doesn't match the request host.
