# Deployment

Production and staging use the same immutable-release mechanism. Each
environment selects one complete backend-plus-frontend release through
`current`; `previous` is its only rollback target.

## Topology

```text
/srv/paperswithcode/
  repository.git
  .venv
  runtime-lock.sha256
  releases/<sha12>-<environment>/
  environments/{production,staging}/{current,previous}

/etc/paperswithcode/{production,staging}.env
/etc/paperswithcode/production-cron.env
/var/lib/paperswithcode/{shared,production,staging}
```

`paperswithcode-backend@production` runs as `pwc-production` on `127.0.0.1:8000`.
`paperswithcode-backend@staging` runs as `pwc-staging` on `127.0.0.1:8001`.
Nginx serves each environment's `current/frontend-dist` and may fall back only
to its `previous` hashed assets. Public staging is static and admin-gated; it
never runs Vite or HMR.

Both environments read the live `public` catalog and shared thumbnail mirror.
Staging connects as `pwc_staging`, can select catalog rows, and can write only
environment-owned user, workflow, and chat rows in the `staging` schema.

## Commands

Read-only status:

```bash
pwc-status
python deploy/topology_audit.py --json
```

Deploy:

```bash
sudo pwc-deploy staging <commit-or-ref>
sudo pwc-deploy production <commit-or-ref> --confirm DEPLOY_PRODUCTION
```

Production accepts only commits reachable from `origin/main`. Every deploy
builds the selected frontend profile, validates manifests and paths, starts a
candidate on `8100-8199`, runs smoke checks, moves only the selected pointer,
restarts only that backend, and rolls back automatically on a failed live
check.

For the one-time migration from a legacy service, qualify without moving the
pointer, then stop the legacy owner and activate the already-qualified release:

```bash
sudo pwc-deploy production <main-sha> \
  --qualify-only --confirm DEPLOY_PRODUCTION
```

`--defer-public-smoke` exists only for the initial bootstrap before nginx points
at the immutable root. It is not a normal release option.

Rollback:

```bash
sudo pwc-rollback staging
sudo pwc-rollback production --confirm ROLLBACK_PRODUCTION
```

Nginx has a separate lifecycle:

```bash
sudo pwc-nginx staging --confirm APPLY_NGINX_STAGING
sudo pwc-nginx production --confirm APPLY_NGINX_PRODUCTION
```

It displays the effective diff, runs `nginx -t`, reloads, and smokes the
selected host. Ordinary deploys never edit or reload nginx.

Install deployment tooling only from committed source:

```bash
sudo python deploy/install_deploy_tools.py <commit>
```

Remove releases not referenced by either environment's `current` or `previous`
pointer:

```bash
sudo pwc-cleanup --confirm CLEAN_RELEASES
```

The union of those four pointers is the complete retention set. Never remove a
release directory by hand.

## Invariants

`release.json` stores the full SHA, build profile, build time, frontend
entrypoint, and backend/frontend feature manifests. `features.json` lives
beside built `index.html`. Startup fails if a deployed shell references
`/src/main.tsx`, assets are missing, paths are relative or inside a release,
or feature manifests disagree.

While chat remains staging-only, production build and runtime configuration
disable it; its backend router is absent and `/chat` redirects home.
Production and staging use host-only `pwc_session` and
`pwc_staging_session` cookies, distinct JWT secrets, and the shared OAuth
client with host-validated callback state.

Codex add-evals and enrich-paper buttons are enabled only in production and
remain protected by Hugging Face admin authentication in both the frontend and
API. Production owns the writable catalog and receives the remote-job
credentials through its protected environment. Staging keeps both controls
disabled because its catalog role is read-only and it has no job credentials.
Each release launcher derives the non-secret capability flags from that
release's validated manifest, so rolling back also restores the matching
frontend/backend feature state.

## Scheduled work and backup

GitHub Actions calls `sudo /usr/local/sbin/pwc-cron <registered-job>`. The
launcher runs as `pwc-cron`, loads production plus CRON-only configuration,
resolves `production/current`, records its release ID, and uses absolute
lock/log directories.

```bash
sudo pwc-cron status
pwc cron health refresh_paper_embeddings --strict --json
```

`pwc-postgres-backup.timer` remains at 03:15 UTC. It runs the backup script from
`production/current` as `pwc-cron`, dumps both `public` and `staging` with the
read-only `pwc_backup` role, verifies the local checksum and remote object
listing, keeps three local dumps, and keeps thirty remote dumps.

The hourly GitHub Actions monitor uses the same
`deploy/smoke_test.py --monitor-subset` implementation as releases. It checks
the production SPA and hashed asset MIME types plus the staging health/auth
boundary without creating an authenticated session.

## Development

Use `uv run --env-file backend/keys.env ...` for local backend commands and
`npm run dev` for a localhost frontend. `start_services.sh` and
`stop_services.sh` are non-mutating retirement notices; `check_services.sh`
delegates to `pwc-status`.
